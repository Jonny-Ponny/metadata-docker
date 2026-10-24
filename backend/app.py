import os
import errno
import shutil
import re
import secrets
import jwt
import datetime
import base64
import re
import requests
import tempfile
from urllib.parse import quote, urlparse
from functools import wraps
from metadata_extractor import *
from metadata_writer import *
from auth import (
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    TOKEN_SCOPE_DOWNLOAD,
    TOKEN_SCOPE_SESSION,
    login as auth_login,
    reset_rate_limiter,
    token_required,
)
from routes import register_blueprints
from routes.system import (
    _compare_versions,
    _version_cache,
    get_version_info,
)
from formats import is_supported_audio, mime_for
from renaming import (
    extract_year,
    find_first_audio,
    generate_name_from_scheme,
    same_path,
    unique_destination,
)
from errors import (
    _json_object,
    _permission_error,
    _server_error,
    register_error_handlers,
)
from paths import (
    generated_rename_path,
    is_library_root,
    is_within as _is_within,
    safe_path as resolve_safe_path,
    unique_path as _unique_path,
)
from pathlib import Path
from zip_stream import iter_zip
from safe_fetch import fetch_image, UnsafeURLError, ImageTooLargeError

from flask import Flask, jsonify, request, send_file, send_from_directory, Response
from logger_config import log_info, log_error, log_warning, LOG_DIR

from plugin_manager import PluginManager
from addon_base import EXTRA_INFO_FIELD
from config import (
    APP_GIT_SHA,
    APP_VERSION,
    AUTH_PASSWORD,
    AUTH_PASSWORD_HASH,
    AUTH_USERNAME,
    CACHE_TTL_SECONDS,
    COVER_UPLOAD_BYTES,
    COVER_UPLOAD_PATHS,
    DEBUG,
    DISABLE_VERSION_CHECK,
    GITHUB_REPO_NAME,
    GITHUB_REPO_OWNER,
    JWT_SECRET_KEY,
    MAX_UPLOAD_BYTES,
    MUSIC_ROOT,
    PGID,
    PUID,
    STORAGE_HEADROOM_BYTES,
    TEXT_MAX_BYTES,
    TOKEN_EXPIRE_HOURS,
    format_size as _format_size,
)

log_info("STARTING")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
# Flask's built-in static route has the same `/<path>` shape as `serve` below
# and shadows it. It is disabled so `serve` is the single place that applies
# cache headers and the SPA fallback.
app = Flask(__name__, static_folder=None)
register_error_handlers(app)
register_blueprints(app)

app.config['SECRET_KEY'] = JWT_SECRET_KEY

def _stream_size(file_storage):
    """Return the size of the uploaded part without consuming it.

    ``Content-Length`` covers the whole multipart body, so it cannot be used
    to compare an existing file. The parsed part is a seekable spooled file.
    """
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return None
    try:
        position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(position)
        return size
    except (OSError, AttributeError, ValueError):
        return None


# Filesystems without hard-link support fall back to an exclusive create.
_HARDLINK_UNSUPPORTED = frozenset({
    errno.EPERM,
    errno.EACCES,
    errno.EMLINK,
    errno.ENOSYS,
    errno.EOPNOTSUPP,
    errno.ENOTSUP,
})


def _claim_upload(temp_path, destination):
    """Give *temp_path* the name *destination* without replacing anything.

    ``os.replace()`` overwrites an existing destination, so two uploads that
    picked the same free name would lose one of the files. ``os.link()`` is
    atomic and fails with ``EEXIST`` instead, which lets the caller try the
    next name. On filesystems without hard links, the destination is claimed
    with an exclusive create before the rename.
    """
    try:
        os.link(temp_path, destination)
    except FileExistsError:
        return False
    except OSError as error:
        if error.errno not in _HARDLINK_UNSUPPORTED:
            raise
        try:
            descriptor = os.open(
                destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
            )
        except FileExistsError:
            return False
        os.close(descriptor)
        try:
            os.replace(temp_path, destination)
        except OSError:
            # Do not leave the zero-byte claim behind if the rename fails.
            try:
                os.remove(destination)
            except OSError:
                pass
            raise
    return True


def _same_size(path, size):
    """Return True when *path* is a file whose size equals *size*."""
    if size is None:
        return False
    try:
        return os.path.isfile(path) and os.path.getsize(path) == size
    except OSError:
        return False


def _save_upload_atomic(file_storage, directory, filename, conflict, size=None):
    """Write an upload to the first free name in *directory*.

    The bytes go to a hidden temp file first, then the destination is claimed
    atomically, so an interrupted client, a full disk or a killed process
    never leaves a truncated track in the library (where ``build_tree`` would
    list it as a normal file) and two concurrent uploads of the same name
    cannot overwrite each other.

    Returns ``(path, skipped)``. Under the "skip-identical" policy, a
    destination that already holds a file of the same size is reported as
    skipped even when it appeared after the initial existence check.
    """
    base, ext = os.path.splitext(filename)
    temp_path = os.path.join(directory, f'.upload-{secrets.token_hex(8)}.part')
    stream = getattr(file_storage, 'stream', None)
    if stream is not None:
        try:
            stream.seek(0)
        except (OSError, AttributeError, ValueError):
            pass
    try:
        file_storage.save(temp_path)

        counter = 0
        candidate = filename
        while True:
            destination = os.path.join(directory, candidate)
            if counter == 0 and os.path.isdir(destination):
                raise IsADirectoryError(destination)
            if _claim_upload(temp_path, destination):
                return destination, False
            if counter == 0 and conflict == UPLOAD_CONFLICT_SKIP_IDENTICAL:
                if _same_size(destination, size):
                    return destination, True
            counter += 1
            candidate = f'{base} ({counter}){ext}'
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# Upload conflict policy. "skip-identical" leaves an existing file untouched
# when the incoming file has the same size, so re-dropping a folder is
# idempotent; anything else gets the usual " (1)" suffix. "keep-both" always
# creates a new name instead of skipping.
UPLOAD_CONFLICT_SKIP_IDENTICAL = 'skip-identical'
UPLOAD_CONFLICT_KEEP_BOTH = 'keep-both'
UPLOAD_CONFLICTS = frozenset({
    UPLOAD_CONFLICT_SKIP_IDENTICAL,
    UPLOAD_CONFLICT_KEEP_BOTH,
})
DEFAULT_UPLOAD_CONFLICT = UPLOAD_CONFLICT_SKIP_IDENTICAL

# Folder creation policy. Uploads merge into an existing folder ("merge"),
# while the New Folder button keeps the previous rename-to-" (1)" behaviour.
MKDIR_CONFLICT_MERGE = 'merge'
MKDIR_CONFLICT_RENAME = 'rename'
MKDIR_CONFLICTS = frozenset({MKDIR_CONFLICT_MERGE, MKDIR_CONFLICT_RENAME})
DEFAULT_MKDIR_CONFLICT = MKDIR_CONFLICT_RENAME

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES


@app.before_request
def limit_cover_upload_size():
    """Apply the smaller body limit to cover-art uploads."""
    if request.path in COVER_UPLOAD_PATHS:
        request.max_content_length = COVER_UPLOAD_BYTES


log_info(f'Debug set to {DEBUG}')
log_info(f'PUID set to {PUID}')
log_info(f'PGID set to {PGID}')

log_info(f'Music folder: {Path(MUSIC_ROOT).absolute()}')
log_info(f'Log folder:{Path(LOG_DIR).absolute()}')
log_info(
    f'Upload limit: {_format_size(MAX_UPLOAD_BYTES)} per request; '
    f'cover images: {_format_size(COVER_UPLOAD_BYTES)}'
)

# ------------------------ADDONS------------------------ #

plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# -------------------------AUTH------------------------- #

# The handler, token scopes and the rate limiter live in auth.py so that
# module never has to import this one.
@app.route('/api/login', methods=['POST'])
def login():
    return auth_login()


# GET /api/validate
# Simple endpoint to check if token is valid
@app.route('/api/validate', methods=['GET'])
@token_required
def validate_token():
    """Simple endpoint to check if token is valid."""
    return jsonify({'valid': True})

# Sort filetree
def natural_key(text):
    """Convert text into a list of strings and numbers for natural sorting.

    ``str.isdigit()`` is true for characters such as ``²`` that ``int()``
    rejects, so only ASCII digits are converted (B-10).
    """
    return [
        int(part) if part.isascii() and part.isdigit() else part.lower()
        for part in re.split(r'(\d+)', text)
    ]

def build_tree(current_path, relative_path):
    items = []
    try:
        entries = sorted(os.listdir(current_path), key=natural_key)
        for entry in entries:
            # Uploads are written to a hidden .upload-*.part file and renamed
            # into place, so a tree reload during a long upload must not list
            # the temporary file. Other dotfiles stay visible.
            if entry.startswith('.upload-') and entry.endswith('.part'):
                continue
            full = os.path.join(current_path, entry)
            rel = os.path.join(relative_path, entry).replace('\\', '/')
            # An entry can disappear between listdir() and stat() when a file
            # is deleted or renamed concurrently. Skip it instead of failing
            # the whole tree with a 500 (B-11).
            if os.path.isdir(full):
                # Symlinked directories are skipped: following them can escape
                # MUSIC_ROOT or recurse forever through a cycle. safe_path()
                # resolves symlinks as well, so anything not listed here could
                # not be opened through the API either.
                if os.path.islink(full):
                    continue
                try:
                    children = build_tree(full, rel)
                    info = os.stat(full)
                except OSError:
                    continue
                items.append({
                    'name': entry,
                    'type': 'directory',
                    'path': rel,
                    'children': children,
                    'created': info.st_ctime,
                    'modified': info.st_mtime,
                    'size': 0
                })
            elif os.path.isfile(full):
                # A symlinked file is only listed when it resolves inside the
                # library. This also avoids calling os.stat() on a link that
                # points at an arbitrary outside file.
                if os.path.islink(full) and not _is_within(MUSIC_ROOT, full):
                    continue
                try:
                    info = os.stat(full)
                except OSError:
                    continue
                # Check for audio files
                if is_supported_audio(entry):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'audio',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })
                # Check for image files
                elif entry.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'image',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })

                elif entry.lower().endswith(('.txt', '.lrc')):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'text',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })
                # Everything else is still listed so it can be inspected,
                # renamed, downloaded or deleted. The metadata endpoint marks
                # these files read-only.
                else:
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'other',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })

    except PermissionError:
        pass

    return items


# Path helpers live in paths.py. These wrappers bind the library root until
# create_app() passes the settings through (Phase 3, step 10).
def _is_library_root(path):
    """Return True when *path* resolves to the music library root itself."""
    return is_library_root(path, MUSIC_ROOT)


def _generated_rename_path(parent, name):
    """Validate a generated rename target and return its full path."""
    return generated_rename_path(parent, name, MUSIC_ROOT)


def safe_path(file_path):
    """Resolve a user-supplied path and keep it inside the music folder."""
    return resolve_safe_path(file_path, MUSIC_ROOT)

# -------------------------API ENDPOINTS------------------------- #

# GET /api/files
# Fetch library structure as filetree
@app.route('/api/files', methods=['GET'])
@token_required
def list_files():
    try:
        tree = build_tree(MUSIC_ROOT, '')
        return jsonify(tree)
    except Exception as e:
        return _server_error(e)

# GET /api/metadata?path=<file_path>&includePicture=<bool>
# Fetch all metadata for a specific file
@app.route('/api/metadata', methods=['GET'])
@token_required
def get_metadata():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    include_picture = request.args.get('includePicture', 'true').lower() != 'false'

    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        metadata = extract_metadata(full_path, include_picture=include_picture)
        if metadata is None:
            # Unsupported files are shown in the tree but cannot be edited.
            # Return an empty read-only payload instead of an error so the UI
            # can display them without a failure toast.
            if not is_supported_audio(full_path):
                return jsonify(read_only_metadata(full_path))
            return jsonify({'error': 'Could not read metadata (unsupported format?)'}), 500

        return jsonify(metadata)

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/file
# Update a single metadata field for one file
@app.route('/api/metadata/file', methods=['POST'])
@token_required
def update_single_file():
    data, error = _json_object()
    if error:
        return error
    file_path = data.get('path')
    field = data.get('field')
    value = data.get('value')
    
    if not file_path or not field:
        return jsonify({'error': 'Missing path or field'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        if not is_supported_audio(full_path):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        success = update_file_metadata(full_path, field, value)
        if success:
            return jsonify({'success': True, 'message': f'Updated {field} for {os.path.basename(file_path)}'})
        else:
            return jsonify({'error': 'Failed to update metadata'}), 500
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/folder
# Update a single metadata field for all files in a folder
@app.route('/api/metadata/folder', methods=['POST'])
@token_required
def update_folder_files():
    data, error = _json_object()
    if error:
        return error
    folder_path = data.get('path')
    field = data.get('field')
    value = data.get('value')
    
    if not folder_path or not field:
        return jsonify({'error': 'Missing path or field'}), 400
    
    try:
        full_path = safe_path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404
        
        # Only process supported audio files in the folder
        results = update_folder_metadata(full_path, field, value)
        
        return jsonify({
            'success': True, 
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': f"Updated {results['updated']} of {results['total']} files"
        })
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# GET /api/audio?path=<file_path>
# Fetch audiofile
@app.route('/api/audio', methods=['GET'])
@token_required
def serve_audio():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        if not is_supported_audio(full_path):
            return jsonify({'error': 'Not an audio file'}), 400
        log_info(f'Serving audio: {full_path}')
        return send_file(full_path, mimetype=mime_for(full_path), conditional=True)
    
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/upload
# Upload file or folder via drag and drop
@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file():
    """Handle file and folder uploads via drag and drop, preserving structure"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    target_path = request.form.get('targetPath', '')
    original_filename = request.form.get('originalFilename') or file.filename
    conflict = (request.form.get('conflict') or DEFAULT_UPLOAD_CONFLICT).strip()

    if conflict not in UPLOAD_CONFLICTS:
        return jsonify({'error': 'Invalid conflict policy'}), 400

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Resolve the destination through safe_path so a crafted targetPath
    # (e.g. "../outside" or "/etc") cannot write outside the library.
    try:
        target_dir = safe_path(target_path)
    except PermissionError as e:
        return _permission_error(e)

    if os.path.exists(target_dir) and not os.path.isdir(target_dir):
        return jsonify({'error': 'Upload target is not a folder'}), 400

    # Keep only the base name - a client-supplied filename must never be able
    # to change the destination directory.
    filename = os.path.basename(str(original_filename).replace('\\', '/'))
    filename = filename.replace('\0', '')
    if filename in ('', '.', '..'):
        return jsonify({'error': 'Invalid filename'}), 400

    # Build the full file path
    file_path = os.path.join(target_dir, filename)
    if not _is_within(target_dir, file_path):
        return jsonify({'error': 'Invalid filename'}), 400

    # Create the target folder only after the name is known to be valid, so a
    # rejected upload does not leave an empty folder behind.
    os.makedirs(target_dir, exist_ok=True)

    incoming_size = _stream_size(file)

    # Resolve duplicate names and claim the destination in one atomic step.
    # Comparing the size makes re-dropping an unchanged folder a no-op instead
    # of producing "name (1).ext" copies.
    try:
        file_path, skipped = _save_upload_atomic(
            file,
            target_dir,
            filename,
            conflict,
            incoming_size,
        )
    except IsADirectoryError:
        return jsonify({'error': 'A folder with that name already exists'}), 400
    except Exception as e:
        return _server_error(e)

    rel_path = os.path.relpath(file_path, MUSIC_ROOT).replace('\\', '/')
    renamed = file_path != os.path.join(target_dir, filename)

    if skipped:
        log_info(f"Skipped identical upload {file_path}")
        return jsonify({
            'success': True,
            'skipped': True,
            'renamed': False,
            'path': rel_path,
            'filename': os.path.basename(file_path),
            'original_filename': original_filename,
        })

    log_info(f"Successfully uploaded {file_path}")

    return jsonify({
        'success': True,
        'skipped': False,
        'renamed': renamed,
        'path': rel_path,  # Normalize path separators
        'filename': os.path.basename(file_path),
        'original_filename': original_filename
    })

# GET /api/storage
# Free space in the library and the temp directory used for upload spooling
@app.route('/api/storage', methods=['GET'])
@token_required
def get_storage():
    """Report free space so the client can reject an oversized drop early."""
    try:
        music = shutil.disk_usage(MUSIC_ROOT)
        temp = shutil.disk_usage(tempfile.gettempdir())
    except OSError as e:
        return _server_error(e)

    return jsonify({
        'music': {'free': music.free, 'total': music.total},
        'temp': {'free': temp.free, 'total': temp.total},
        'headroom': STORAGE_HEADROOM_BYTES,
    })

# POST /api/mkdir
# Create a new directory
@app.route('/api/mkdir', methods=['POST'])
@token_required
def create_directory():
    """Create a new directory.

    ``conflict="rename"`` (the default, used by the New Folder button) appends
    " (n)" to an existing name. ``conflict="merge"`` returns the existing
    folder so an upload writes into it instead of creating a stray copy.
    """
    data, error = _json_object()
    if error:
        return error
    desired_path = data.get('path', '')
    conflict = (data.get('conflict') or DEFAULT_MKDIR_CONFLICT).strip()
    if not desired_path:
        return jsonify({'error': 'No path provided'}), 400
    if conflict not in MKDIR_CONFLICTS:
        return jsonify({'error': 'Invalid conflict policy'}), 400

    try:
        full_path = safe_path(desired_path)
        if _is_library_root(full_path):
            return jsonify({'error': 'Cannot create the library root'}), 400

        if conflict == MKDIR_CONFLICT_MERGE:
            # Idempotent by design: concurrent uploads of the same new folder
            # all call this route. A "does it exist?" check followed by a
            # non-exclusive makedirs would race - the second worker sees no
            # folder, then gets FileExistsError - which surfaced as
            # "The destination already exists." on a brand-new folder.
            existed = os.path.isdir(full_path)
            try:
                os.makedirs(full_path, exist_ok=True)
            except FileExistsError:
                # A file (not a folder) occupies the name.
                return jsonify({'error': 'A file with that name already exists'}), 400
            except NotADirectoryError:
                return jsonify({'error': 'A file with that name already exists'}), 400
            if not os.path.isdir(full_path):
                return jsonify({'error': 'A file with that name already exists'}), 400
            created = not existed
        else:
            # New Folder button: keep the historical rename-to-" (1)" policy,
            # but retry if another request claims the name between the free
            # name search and the actual creation.
            created = True
            if os.path.exists(full_path):
                full_path = _unique_path(full_path)
            while True:
                try:
                    os.makedirs(full_path, exist_ok=False)
                    break
                except FileExistsError:
                    full_path = _unique_path(full_path)

        if not _is_within(MUSIC_ROOT, full_path):
            return jsonify({'error': 'Invalid destination'}), 400

        rel_path = os.path.relpath(full_path, MUSIC_ROOT).replace('\\', '/')

        log_info(
            f"{'Created new directory' if created else 'Reused directory'} {full_path}"
        )

        return jsonify({'success': True, 'path': rel_path, 'created': created})

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/rename
# Rename a file or directory
@app.route('/api/rename', methods=['POST'])
@token_required
def rename_item():
    """Rename a file or folder."""
    data, error = _json_object()
    if error:
        return error
    old_path = data.get('oldPath')
    new_name = data.get('newName')   # only the new base name, not full path

    if not old_path or not new_name:
        return jsonify({'error': 'Missing oldPath or newName'}), 400

    try:
        full_old = safe_path(old_path)
        if not os.path.exists(full_old):
            return jsonify({'error': 'Path not found'}), 404

        # Build new full path: same parent directory + new name
        parent = os.path.dirname(full_old)

        # Prevent directory traversal in the new name: it must be a bare
        # filename, not a path.
        if not isinstance(new_name, str) or '\0' in new_name or '/' in new_name or '\\' in new_name:
            return jsonify({'error': 'Invalid new name'}), 400
        if new_name in ('.', '..'):
            return jsonify({'error': 'Invalid new name'}), 400

        full_new = os.path.join(parent, new_name)
        if not _is_within(MUSIC_ROOT, full_new):
            return jsonify({'error': 'Invalid new name'}), 400

        # os.rename() replaces an existing destination on POSIX. Refuse that
        # unless both names refer to the same item (a no-op rename).
        if os.path.lexists(full_new) and full_new != full_old:
            try:
                same_item = os.path.samefile(full_old, full_new)
            except OSError:
                same_item = False
            if not same_item:
                return jsonify({'error': 'An item with that name already exists'}), 409

        os.rename(full_old, full_new)

        log_info(f"Renamed {full_old} to {full_new}")

        # Return the new relative path
        new_rel = os.path.relpath(full_new, MUSIC_ROOT).replace('\\', '/')
        return jsonify({'success': True, 'newPath': new_rel})
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/delete
# Delete a file or folder
@app.route('/api/delete', methods=['POST'])
@token_required
def delete_item():
    """Delete a file or folder."""
    data, error = _json_object()
    if error:
        return error
    path = data.get('path')

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    try:
        full_path = safe_path(path)
        if _is_library_root(full_path):
            return jsonify({'error': 'Cannot delete the library root'}), 400
        if not os.path.lexists(full_path):
            return jsonify({'error': 'Path not found'}), 404

        # A symlink is removed itself, never the target it points at. This also
        # lets users clean up symlinks without rmtree() refusing the path.
        if os.path.islink(full_path) or os.path.isfile(full_path):
            os.remove(full_path)
            log_info(f"Deleted {full_path}")
        else:
            shutil.rmtree(full_path)
            log_info(f"Deleted {full_path} and its contents")


        return jsonify({'success': True})
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/move
# Move a file or folder to a new destination folder
@app.route('/api/move', methods=['POST'])
@token_required
def move_item():
    """Move a file or folder to a new destination folder."""
    data, error = _json_object()
    if error:
        return error
    source = data.get('source')
    destination = data.get('destination')  # destination folder path (empty = root)

    if not source or destination is None:
        return jsonify({'error': 'Missing source or destination'}), 400

    try:
        source_full = safe_path(source)
        if not os.path.exists(source_full):
            return jsonify({'error': 'Source not found'}), 404

        # Build destination full path
        if destination:
            dest_full = safe_path(destination)
            if not os.path.isdir(dest_full):
                return jsonify({'error': 'Destination is not a directory or does not exist'}), 400
        else:
            dest_full = MUSIC_ROOT

        # New full path: destination + basename of source
        new_full = os.path.join(dest_full, os.path.basename(source_full))

        # Prevent directory traversal
        if not _is_within(MUSIC_ROOT, new_full):
            return jsonify({'error': 'Invalid destination'}), 400

        # If source is a directory, ensure destination is not inside source.
        # realpath containment also catches the same folder reached through a
        # symlink alias, which a string prefix check would miss.
        if os.path.isdir(source_full) and _is_within(source_full, dest_full):
            return jsonify({
                'error': 'Cannot move a folder into itself or its own subfolder'
            }), 400

        # Handle name conflict
        if os.path.exists(new_full):
            return jsonify({'error': 'An item with that name already exists in the destination'}), 409

        # Perform the move
        shutil.move(source_full, new_full)

        log_info(f"Moved {source_full} to {new_full}")

        # Return the new relative path
        new_rel = os.path.relpath(new_full, MUSIC_ROOT).replace('\\', '/')
        return jsonify({'success': True, 'newPath': new_rel})

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)
    
# POST /api/copy
# Create a copy of file/directory
@app.route('/api/copy', methods=['POST'])
@token_required
def copy_item():
    data, error = _json_object()
    if error:
        return error
    path = data.get('path')

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    try:
        full_path = safe_path(path)
        if not os.path.exists(full_path):
            return jsonify({'error': 'Path not found'}), 404

        if _is_library_root(full_path):
            return jsonify({'error': 'Cannot copy the library root'}), 400

        # File
        if os.path.isfile(full_path):
            filename, file_extension = os.path.splitext(full_path)
            new_name = filename + ' - Copy' + file_extension
            if os.path.exists(new_name):
                base = filename
                extension = file_extension
                counter = 1
                while os.path.exists(new_name):
                    new_name = f'{base} - Copy({counter}){extension}'
                    counter += 1
            if not _is_within(MUSIC_ROOT, new_name):
                return jsonify({'error': 'Invalid destination'}), 400
            shutil.copy2(full_path, new_name)
            
        # Directory
        else:
            new_name = full_path + ' - Copy'
            if os.path.exists(new_name):
                base = new_name
                counter = 1
                while os.path.exists(new_name):
                    new_name = f'{base} ({counter})'
                    counter += 1
            if not _is_within(MUSIC_ROOT, new_name):
                return jsonify({'error': 'Invalid destination'}), 400
            # Preserve symlinks as links. Following them would copy the target
            # from outside the library into the new folder.
            shutil.copytree(full_path, new_name, symlinks=True)
        
        log_info(f"Created a copy of {full_path}")

        return jsonify({'success': True})
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/picture/file
# Update cover art for a single file
@app.route('/api/metadata/picture/file', methods=['POST'])
@token_required
def update_file_picture_endpoint():
    """Update cover art for a single file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    image_file = request.files['file']
    file_path = request.form.get('path')
    
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        if not is_supported_audio(full_path):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        # Read image data
        image_data = image_file.read()
        mime_type = image_file.mimetype
        
        success = update_file_picture(full_path, image_data, mime_type)
        
        if success:
            # Get updated metadata to return new picture data
            metadata = extract_metadata(full_path)
            
            return jsonify({
                'success': True, 
                'message': f'Updated cover art for {os.path.basename(file_path)}',
                'picture': (metadata or {}).get('picture')
            })
        else:
            return jsonify({'error': 'Failed to update cover art'}), 500
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/picture/url
# Update cover art for a single file using a remote URL
@app.route('/api/metadata/picture/url', methods=['POST'])
@token_required
def update_file_picture_from_url_endpoint():
    data, error = _json_object()
    if error:
        return error
    image_url = data.get('url')
    file_path = data.get('path')
    
    if not image_url or not file_path:
        return jsonify({'error': 'Missing url or path parameter'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        # Check the format before spending a network request: an unsupported
        # target cannot store a picture and would only produce a 500 later.
        if not is_supported_audio(full_path):
            return jsonify({'error': 'Unsupported file format'}), 400

        # 1. Fetch the image through the SSRF guard (public http/https only,
        # validated redirects, streamed with a size cap and timeouts).
        user_agent = f'metadata-docker/{APP_VERSION}'
        image_data, mime_type = fetch_image(image_url, user_agent)
        
        # 2. Apply coverart
        success = update_file_picture(full_path, image_data, mime_type)
        
        if success:
            metadata = extract_metadata(full_path)
            return jsonify({
                'success': True, 
                'message': f'Updated cover art for {os.path.basename(file_path)}',
                'picture': (metadata or {}).get('picture')
            })
        return jsonify({'error': 'Failed to update cover art'}), 500
            
    except ImageTooLargeError as e:
        return jsonify({'error': str(e)}), 413
    except UnsafeURLError as e:
        return jsonify({'error': str(e)}), 400
    except requests.exceptions.RequestException as e:
        return _server_error(e, 'Could not download the image from the provided URL.')
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)


# GET /api/metadata/picture/preview?url=<remote image URL>
# Proxy a remote cover for display in the UI. This keeps the browser from
# contacting arbitrary hosts directly and reuses the same SSRF guard as the
# apply-cover endpoint.
PREVIEW_MAX_BYTES = 5 * 1024 * 1024


@app.route('/api/metadata/picture/preview', methods=['GET'])
@token_required
def preview_remote_picture():
    image_url = request.args.get('url')
    if not image_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    try:
        image_data, mime_type = fetch_image(
            image_url,
            f'metadata-docker/{APP_VERSION}',
            max_bytes=PREVIEW_MAX_BYTES,
        )
    except ImageTooLargeError as e:
        return jsonify({'error': str(e)}), 413
    except UnsafeURLError as e:
        return jsonify({'error': str(e)}), 400
    except requests.exceptions.RequestException as e:
        return _server_error(e, 'Could not download the image from the provided URL.')

    response = Response(image_data, mimetype=mime_type)
    response.headers['Cache-Control'] = 'private, max-age=300'
    response.headers['Content-Disposition'] = 'inline'
    return response


# POST /api/metadata/picture/folder
# Update cover art for all files in a folder
@app.route('/api/metadata/picture/folder', methods=['POST'])
@token_required
def update_folder_pictures_endpoint():
    """Update cover art for all files in a folder."""
    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    image_file = request.files['file']
    folder_path = request.form.get('path')
    
    if folder_path is None:  # Allow empty string for root
        return jsonify({'error': 'Missing path parameter'}), 400
    
    try:
        full_path = safe_path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404
        
        # Read image data
        image_data = image_file.read()
        mime_type = image_file.mimetype
        
        # Update all files in folder
        results = update_folder_pictures(full_path, image_data, mime_type)
        
        return jsonify({
            'success': True, 
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': f"Updated cover art for {results['updated']} of {results['total']} files"
        })
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)
    
# POST /api/metadata/folder/current
# Update a single metadata field for all files in a folder (current folder only, no subfolders)
@app.route('/api/metadata/folder/current', methods=['POST'])
@token_required
def update_folder_files_current_only():
    data, error = _json_object()
    if error:
        return error
    folder_path = data.get('path')
    field = data.get('field')
    value = data.get('value')
    
    if not folder_path or not field:
        return jsonify({'error': 'Missing path or field'}), 400
    
    try:
        full_path = safe_path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404
        
        # Only process files in the current folder (no recursion)
        results = update_folder_metadata_only_current(full_path, field, value)
        
        return jsonify({
            'success': True, 
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': f"Updated {results['updated']} of {results['total']} files in current folder"
        })
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/picture/folder/current
# Update cover art for all files in a folder (current folder only, no subfolders)
@app.route('/api/metadata/picture/folder/current', methods=['POST'])
@token_required
def update_folder_pictures_current_only_endpoint():
    """Update cover art for all files in a folder (current folder only, no subfolders)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    image_file = request.files['file']
    folder_path = request.form.get('path')
    
    if folder_path is None:  # Allow empty string for root
        return jsonify({'error': 'Missing path parameter'}), 400
    
    try:
        full_path = safe_path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404
        
        # Read image data
        image_data = image_file.read()
        mime_type = image_file.mimetype
        
        # Update all files in current folder only (no recursion)
        results = update_folder_pictures_only_current(full_path, image_data, mime_type)
        
        return jsonify({
            'success': True, 
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': f"Updated cover art for {results['updated']} of {results['total']} files in current folder"
        })
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)


# POST /api/metadata/field/delete
# Delete a specific metadata field from a file or all files in a folder
@app.route('/api/metadata/field/delete', methods=['POST'])
@token_required
def delete_metadata_field():
    """Delete a specific metadata field from a file or all files in a folder."""
    data, error = _json_object()
    if error:
        return error
    path = data.get('path')
    field = data.get('field')
    recursive = data.get('recursive', False)  # Add recursive flag
    
    if not path or not field:
        return jsonify({'error': 'Missing path or field'}), 400
    
    try:
        full_path = safe_path(path)

        if not os.path.isdir(full_path) and not os.path.isfile(full_path):
            return jsonify({'error': 'Path not found'}), 404

        # Check if it's a folder
        if os.path.isdir(full_path):
            # Delete field from all files in folder
            results = delete_field_from_folder(full_path, field, recursive)
            
            return jsonify({
                'success': True, 
                'updated': results['updated'],
                'failed': results['failed'],
                'total': results['total'],
                'message': f"Deleted '{field}' from {results['updated']} of {results['total']} files"
            })
        else:
            # Single file deletion (existing behavior)
            if not is_supported_audio(full_path):
                return jsonify({'error': 'Unsupported file format'}), 400

            from metadata_writer import delete_metadata_field as delete_field
            success = delete_field(full_path, field)
            
            if success:
                return jsonify({'success': True, 'message': f'Deleted {field} from {os.path.basename(path)}'})
            else:
                return jsonify({'error': 'Failed to delete field'}), 500
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/picture/delete
# Delete cover art from a file
@app.route('/api/metadata/picture/delete', methods=['POST'])
@token_required
def delete_cover_art():
    """Delete cover art from a file."""
    data, error = _json_object()
    if error:
        return error
    file_path = data.get('path')
    
    if not file_path:
        return jsonify({'error': 'Missing path'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        if not is_supported_audio(full_path):
            return jsonify({'error': 'Unsupported file format'}), 400

        from metadata_writer import delete_cover_art as delete_cover
        success = delete_cover(full_path)

        log_info(f"Deleted cover art from {full_path}")
        
        if success:
            # Get updated metadata to confirm deletion
            metadata = extract_metadata(full_path)
            
            return jsonify({
                'success': True, 
                'message': f'Deleted cover art from {os.path.basename(file_path)}',
                'picture': (metadata or {}).get('picture')
            })
        else:
            return jsonify({'error': 'Failed to delete cover art'}), 500
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# GET /api/image
# Fetch image
@app.route('/api/image', methods=['GET'])
@token_required
def serve_image():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Determine mimetype. Only the image types listed in the tree are
        # served; anything else would expose arbitrary library files through a
        # content-type-free endpoint.
        ext = os.path.splitext(full_path)[1].lower()
        mimetypes = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        mimetype = mimetypes.get(ext)
        if mimetype is None:
            return jsonify({'error': 'Not an image file'}), 400
        
        return send_file(full_path, mimetype=mimetype)
    
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/picture/save-as-file
# Extract cover art from audio file and save as cover.jpg in the same folder
@app.route('/api/metadata/picture/save-as-file', methods=['POST'])
@token_required
def save_cover_art_as_file():
    """Extract cover art from audio file and save as cover.jpg in the same folder."""
    data, error = _json_object()
    if error:
        return error
    file_path = data.get('path')
    
    if not file_path:
        return jsonify({'error': 'Missing path'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        if not is_supported_audio(full_path):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        metadata = extract_metadata(full_path)
        
        if not (metadata or {}).get('picture'):
            return jsonify({'error': 'No cover art found in file'}), 404
        
        # Extract image data from base64. A corrupt tag value must be a clear
        # 400 rather than an unhandled binascii error.
        picture_data = metadata['picture']
        try:
            if picture_data.startswith('data:image'):
                # Format: data:image/jpeg;base64,/9j/4AAQ...
                header, encoded = picture_data.split(',', 1)
                image_data = base64.b64decode(encoded)

                # Determine extension from mime type
                mime_match = re.search(r'image/(\w+)', header)
                ext = mime_match.group(1) if mime_match else 'jpg'
                if ext == 'jpeg':
                    ext = 'jpg'
            else:
                # Assume it's already base64 without header
                image_data = base64.b64decode(picture_data)
                ext = 'jpg'  # default
        except ValueError:
            # binascii.Error subclasses ValueError.
            return jsonify({'error': 'The cover art data is not valid base64'}), 400
        
        # Save to same folder as the audio file
        folder_path = os.path.dirname(full_path)
        output_path = os.path.join(folder_path, f'cover.{ext}')
        
        # Handle existing file
        if os.path.exists(output_path):
            base = os.path.join(folder_path, 'cover')
            counter = 1
            while os.path.exists(output_path):
                output_path = f'{base} ({counter}).{ext}'
                counter += 1
        
        with open(output_path, 'wb') as f:
            f.write(image_data)

        log_info(f'Created {output_path}')
        
        return jsonify({
            'success': True,
            'message': f'Cover art saved as {os.path.basename(output_path)}',
            'path': os.path.relpath(output_path, MUSIC_ROOT).replace('\\', '/')
        })
        
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/apply-renaming-scheme
# Apply renaming scheme to folder or file
@app.route('/api/apply-renaming-scheme', methods=['POST'])
@token_required
def apply_renaming_scheme():
    """Apply a renaming scheme to a folder or file."""
    data, error = _json_object()
    if error:
        return error
    path = data.get('path')
    scheme = data.get('scheme')
    is_folder = data.get('isFolder', True)
    replace_spaces = data.get('replaceSpaces', False)
    
    if not isinstance(path, str) or not path:
        return jsonify({'error': 'Missing path or scheme'}), 400
    if not isinstance(scheme, str) or not scheme:
        return jsonify({'error': 'Missing path or scheme'}), 400
    if not isinstance(is_folder, bool):
        return jsonify({'error': 'isFolder must be a boolean'}), 400
    if not isinstance(replace_spaces, bool):
        return jsonify({'error': 'replaceSpaces must be a boolean'}), 400
    
    try:
        full_path = safe_path(path)
        
        if is_folder:
            # Handle folder rename
            if not os.path.isdir(full_path):
                return jsonify({'error': 'Folder not found'}), 404
            
            first_audio = find_first_audio(full_path)
            if not first_audio:
                return jsonify({'error': 'No audio files found in folder to extract metadata'}), 400
            
            metadata = extract_metadata(first_audio)
            if metadata is None:
                return jsonify({'error': 'Could not read metadata from the audio file'}), 400
            
            try:
                new_name = generate_name_from_scheme(scheme, metadata, replace_spaces)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            
            if not new_name:
                return jsonify({'error': 'Generated name is empty'}), 400
            
            # Rename folder. The generated name is validated like any other
            # destination so tag values cannot redirect the rename.
            parent = os.path.dirname(full_path)
            try:
                new_path = _generated_rename_path(parent, new_name)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

            # If it already matches the scheme, do not rename
            if same_path(new_path, full_path):
                return jsonify({
                    'success': True,
                    'newPath': os.path.relpath(full_path, MUSIC_ROOT).replace('\\', '/'),
                    'newName': os.path.basename(full_path)
                })
            
            new_path = unique_destination(new_path, is_folder)
            
            if not _is_within(MUSIC_ROOT, new_path):
                return jsonify({'error': 'Invalid generated name'}), 400
            os.rename(full_path, new_path)
            
            log_info(f"Smart renamed folder {full_path} to {new_path}")
            
            return jsonify({
                'success': True,
                'newPath': os.path.relpath(new_path, MUSIC_ROOT).replace('\\', '/'),
                'newName': new_name
            })
            
        else:
            # Handle file rename
            if not os.path.isfile(full_path):
                return jsonify({'error': 'File not found'}), 404
            
            if not is_supported_audio(full_path):
                return jsonify({'error': 'Smart rename only works on supported audio files'}), 400
            
            # Extract metadata from the file itself
            metadata = extract_metadata(full_path)
            if metadata is None:
                return jsonify({'error': 'Could not read metadata from the audio file'}), 400
            
            try:
                new_name_without_ext = generate_name_from_scheme(scheme, metadata, replace_spaces)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            
            if not new_name_without_ext:
                return jsonify({'error': 'Generated name is empty'}), 400
            if new_name_without_ext in ('.', '..'):
                return jsonify({'error': 'Invalid generated name'}), 400
            
            # Add original extension
            ext = os.path.splitext(full_path)[1]
            new_name = new_name_without_ext + ext
            
            parent = os.path.dirname(full_path)
            try:
                new_path = _generated_rename_path(parent, new_name)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            
            # If it already matches the scheme, do not rename
            if same_path(new_path, full_path):
                return jsonify({
                    'success': True,
                    'newPath': os.path.relpath(full_path, MUSIC_ROOT).replace('\\', '/'),
                    'newName': os.path.basename(full_path)
                })
            
            new_path = unique_destination(new_path, is_folder)
            
            if not _is_within(MUSIC_ROOT, new_path):
                return jsonify({'error': 'Invalid generated name'}), 400
            os.rename(full_path, new_path)
            
            log_info(f"Smart renamed file {full_path} to {new_path}")
            
            return jsonify({
                'success': True,
                'newPath': os.path.relpath(new_path, MUSIC_ROOT).replace('\\', '/'),
                'newName': os.path.basename(new_path)
            })
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e, 'Smart rename failed.')


# Download tokens are short-lived so they can be used in a native browser
# download URL without exposing the long-lived auth token.
DOWNLOAD_TOKEN_EXPIRE_SECONDS = 120


def _content_disposition(filename):
    """Return a download header that survives non-Latin-1 file names."""
    fallback = ''.join(
        char if 32 <= ord(char) < 127 and char not in '"\\' else '_'
        for char in filename
    )
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _send_download(path, is_folder):
    """Build the download response for a file or folder."""
    try:
        full_path = safe_path(path)
        if not os.path.exists(full_path):
            return jsonify({'error': 'Path not found'}), 404
        
        # Handle single file download
        if not is_folder and os.path.isfile(full_path):
            # Determine mimetype using the format registry, with image
            # fallbacks for non-audio downloads.
            ext = os.path.splitext(full_path)[1].lower()
            image_mimetypes = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp'
            }
            mimetype = mime_for(
                full_path,
                default=image_mimetypes.get(ext, 'application/octet-stream'),
            )
            
            log_info(f'Downloading file: {full_path}')
            filename = os.path.basename(full_path)
            response = send_file(
                full_path,
                mimetype=mimetype,
                as_attachment=True,
                download_name=filename,
            )
            response.headers['Content-Disposition'] = _content_disposition(filename)
            return response
        
        # Handle folder download as ZIP
        elif os.path.isdir(full_path):
            archive_name = f'{os.path.basename(full_path)}.zip'

            log_info(f'Streaming folder as ZIP: {full_path}')
            response = Response(
                iter_zip(full_path),
                mimetype='application/zip',
            )
            # Content-Length is unknown while streaming, so let the browser
            # save the file under the folder's name.
            response.headers['Content-Disposition'] = _content_disposition(
                archive_name
            )
            # Ask reverse proxies not to buffer the whole archive first.
            response.headers['X-Accel-Buffering'] = 'no'
            return response
        else:
            return jsonify({'error': 'Invalid item type'}), 400
            
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e, 'The download could not be completed.')


# POST /api/download-token
# Create a short-lived token for a native browser download
@app.route('/api/download-token', methods=['POST'])
@token_required
def create_download_token():
    """Create a short-lived token authorizing one file/folder download."""
    data, error = _json_object()
    if error:
        return error
    path = data.get('path')
    is_folder = bool(data.get('isFolder', False))

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    try:
        full_path = safe_path(path)
        if not os.path.exists(full_path):
            return jsonify({'error': 'Path not found'}), 404
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e, 'Could not create a download token.')

    filename = os.path.basename(os.path.normpath(path)) or 'download'
    if is_folder:
        filename = f'{filename}.zip'

    token = jwt.encode({
        'username': AUTH_USERNAME,
        'scope': TOKEN_SCOPE_DOWNLOAD,
        'path': path,
        'isFolder': is_folder,
        'exp': datetime.datetime.now() + datetime.timedelta(seconds=DOWNLOAD_TOKEN_EXPIRE_SECONDS)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({
        'token': token,
        'filename': filename,
        'expires_in': DOWNLOAD_TOKEN_EXPIRE_SECONDS
    })


# GET /api/download?token=<short-lived-download-token>
# Allows the browser to handle the download natively
@app.route('/api/download', methods=['GET'])
def download_item_with_token():
    """Download a file or folder using a short-lived download token."""
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Token is missing'}), 401

    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Download link has expired'}), 401
    except Exception:
        return jsonify({'error': 'Token is invalid'}), 401

    if data.get('scope') != TOKEN_SCOPE_DOWNLOAD or not data.get('path'):
        return jsonify({'error': 'Token is invalid'}), 401

    if data.get('username') != AUTH_USERNAME:
        return jsonify({'error': 'Token is invalid'}), 401

    return _send_download(data['path'], bool(data.get('isFolder', False)))


# POST /api/download
# Download a file or folder as a ZIP archive
@app.route('/api/download', methods=['POST'])
@token_required
def download_item():
    """Download a file or folder as a ZIP archive."""
    data, error = _json_object()
    if error:
        return error
    path = data.get('path')
    is_folder = data.get('isFolder', False)

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    return _send_download(path, bool(is_folder))


# Addons historically returned release dates under "year", track numbers under
# "track", and disk numbers under "disk". The main fields are now "date",
# "trackNumber", and "diskNumber", so keep old addons working without writing
# YEAR/TRACK/DISK tags.
def _normalize_addon_metadata(metadata):
    if not isinstance(metadata, dict):
        return metadata
    normalized = dict(metadata)
    for legacy, current in (
        ('year', 'date'),
        ('track', 'trackNumber'),
        ('disk', 'diskNumber'),
        ('extra_info', EXTRA_INFO_FIELD),
    ):
        if legacy in normalized and not normalized.get(current):
            normalized[current] = normalized.pop(legacy)
    return normalized

# Addon endpoints
def _addon_version(fetcher_cls):
    value = getattr(fetcher_cls, 'version', '')
    return '' if value is None else str(value).strip()


def _addon_github_url(fetcher_cls):
    """Return a validated GitHub URL declared by an addon, if any."""
    raw = ''
    for attr in ('github', 'github_url', 'github_link', 'repository', 'homepage'):
        value = getattr(fetcher_cls, attr, '')
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            break

    if raw.startswith(('github.com/', 'www.github.com/')):
        raw = 'https://' + raw
    if not raw:
        return ''

    parsed = urlparse(raw)
    if parsed.scheme != 'https':
        return ''
    if parsed.username or parsed.password:
        return ''
    if (parsed.hostname or '').lower() not in ('github.com', 'www.github.com'):
        return ''
    return raw


@app.route('/api/addons', methods=['GET'])
@token_required
def list_addons():
    result = []
    for fetcher_id, fetcher_cls in plugin_manager.fetchers.items():
        try:
            # Check which methods are actually implemented (not NotImplementedError)
            methods = []
            instance = fetcher_cls()
            
            if not getattr(instance.search_albums, '_default_implementation', False):
                methods.append('search_albums')
            if not getattr(instance.fetch_album_metadata, '_default_implementation', False):
                methods.append('fetch_album_metadata')
            if not getattr(instance.search_songs, '_default_implementation', False):
                methods.append('search_songs')
            if not getattr(instance.fetch_song_metadata, '_default_implementation', False):
                methods.append('fetch_song_metadata')

            result.append({
                "id": fetcher_cls.id,
                "name": fetcher_cls.name,
                "description": fetcher_cls.description,
                "version": _addon_version(fetcher_cls),
                "github": _addon_github_url(fetcher_cls),
                "required_env_vars": getattr(fetcher_cls, 'required_env_vars', []),
                "methods": methods
            })
        except Exception as e:
            log_error(f"Fetcher '{fetcher_id}' failed to initialize: {e}")
            # Skip fetcher if any exception raised
            continue
    return jsonify({"fetchers": result})

# Songs
@app.route('/api/addons/<fetcher_id>/search_songs', methods=['GET'])
@token_required
def search_songs(fetcher_id):
    query = request.args.get('query')
    limit = max(1, min(request.args.get('limit', 5, type=int), 50))

    if not query:
        return jsonify({"success": False, "error": "Missing 'query' parameter"}), 400

    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        results = instance.search_songs(query, limit)
        results = [_normalize_addon_metadata(result) for result in results]
        return jsonify({"success": True, "results": results})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Song search not supported by this fetcher"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)

@app.route('/api/addons/<fetcher_id>/fetch_song/<song_id>', methods=['GET'])
@token_required
def fetch_song_metadata(fetcher_id, song_id):
    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        metadata = instance.fetch_song_metadata(song_id)
        return jsonify({"success": True, "metadata": _normalize_addon_metadata(metadata)})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Fetch song metadata not supported"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)


# Albums
@app.route('/api/addons/<fetcher_id>/search_albums', methods=['GET'])
@token_required
def search_albums(fetcher_id):
    query = request.args.get('query')
    limit = max(1, min(request.args.get('limit', 5, type=int), 50))

    if not query:
        return jsonify({"success": False, "error": "Missing 'query' parameter"}), 400

    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        results = instance.search_albums(query, limit)
        results = [_normalize_addon_metadata(result) for result in results]
        return jsonify({"success": True, "results": results})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Album search not supported by this fetcher"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)

@app.route('/api/addons/<fetcher_id>/fetch_album/<album_id>', methods=['GET'])
@token_required
def fetch_album_metadata(fetcher_id, album_id):
    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        metadata = instance.fetch_album_metadata(album_id)
        if isinstance(metadata, list):
            metadata = [_normalize_addon_metadata(track) for track in metadata]
        else:
            metadata = _normalize_addon_metadata(metadata)
        return jsonify({"success": True, "metadata": metadata})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Fetch album metadata not supported"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)


# Serve Svelte frontend
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    # Unknown API routes are never the SPA: a JSON parse error in the browser
    # would be more confusing than a clear 404.
    if path.startswith('api/'):
        return jsonify({'success': False, 'error': 'Not found'}), 404

    if path and os.path.isfile(os.path.join(STATIC_DIR, path)):
        response = send_from_directory(STATIC_DIR, path)
        # Vite fingerprints the files under assets/, so a given name never
        # changes; everything else is revalidated.
        if path.startswith('assets/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        else:
            response.headers['Cache-Control'] = 'no-cache'
        return response

    # A missing hashed asset must not fall back to HTML; the browser would
    # report a MIME-type error instead of a missing file.
    if path.startswith('assets/'):
        return '', 404

    response = send_from_directory(STATIC_DIR, 'index.html')
    # index.html references hashed asset names. If it is cached, a rebuilt
    # image keeps loading the previous JS bundle after an update.
    response.headers['Cache-Control'] = 'no-cache'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=DEBUG)