import os
import errno
import shutil
import re
import hmac
import secrets
import threading
import jwt
import datetime
import base64
import re
import requests
import tempfile
import time
from urllib.parse import quote, urlparse
from functools import wraps
from metadata_extractor import *
from metadata_writer import *
from formats import is_supported_audio, mime_for
from pathlib import Path
from zip_stream import iter_zip
from safe_fetch import fetch_image, UnsafeURLError, ImageTooLargeError

from flask import Flask, jsonify, request, send_file, send_from_directory, Response
from werkzeug.security import check_password_hash
from logger_config import log_info, log_error, log_warning, LOG_DIR

from plugin_manager import PluginManager
from addon_base import EXTRA_INFO_FIELD

log_info("STARTING")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
# Flask's built-in static route has the same `/<path>` shape as `serve` below
# and shadows it. It is disabled so `serve` is the single place that applies
# cache headers and the SPA fallback.
app = Flask(__name__, static_folder=None)

# Auth config from environment. Missing or empty credentials never fall back
# to a known default. Instead, generate temporary random credentials for this
# process and log them once, so an unconfigured deployment cannot be accessed
# with a guessable password. Set AUTH_USERNAME and AUTH_PASSWORD (or
# AUTH_PASSWORD_HASH) for a stable login.
AUTH_USERNAME = os.getenv('AUTH_USERNAME') or ''
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD') or ''
AUTH_PASSWORD_HASH = os.getenv('AUTH_PASSWORD_HASH') or ''

_generated_username = not AUTH_USERNAME
_generated_password = False

if _generated_username:
    AUTH_USERNAME = f'admin_{secrets.token_hex(4)}'

if AUTH_PASSWORD_HASH and AUTH_PASSWORD:
    log_warning('Both AUTH_PASSWORD and AUTH_PASSWORD_HASH are set; using AUTH_PASSWORD_HASH')
    AUTH_PASSWORD = ''

if AUTH_PASSWORD_HASH:
    # Validate the hash at startup so a typo fails loudly instead of every
    # login returning a 500 or silently never matching. Werkzeug hashes look
    # like "scrypt:...$salt$hash" (or the older pbkdf2 format).
    hash_error = None
    if AUTH_PASSWORD_HASH.count('$') < 2:
        hash_error = 'expected "method$salt$hash"'
    else:
        try:
            check_password_hash(AUTH_PASSWORD_HASH, 'startup-validation')
        except (ValueError, TypeError) as e:
            hash_error = str(e)
    if hash_error:
        raise RuntimeError(
            f'AUTH_PASSWORD_HASH is not a valid Werkzeug password hash ({hash_error}). '
            'Generate one with: python -c "from werkzeug.security import '
            'generate_password_hash; print(generate_password_hash(\'your-password\'))"'
        )
elif not AUTH_PASSWORD:
    AUTH_PASSWORD = secrets.token_urlsafe(24)
    _generated_password = True

if _generated_username or _generated_password:
    log_warning('=' * 70)
    log_warning('AUTH_USERNAME/AUTH_PASSWORD are not fully configured.')
    log_warning('Temporary credentials for this run (they change on every restart):')
    log_warning(f'  username: {AUTH_USERNAME}{" (generated)" if _generated_username else ""}')
    if _generated_password:
        log_warning(f'  password: {AUTH_PASSWORD} (generated)')
    elif AUTH_PASSWORD_HASH:
        log_warning('  password: (from AUTH_PASSWORD_HASH)')
    else:
        log_warning('  password: (from AUTH_PASSWORD)')
    log_warning('Set AUTH_USERNAME and AUTH_PASSWORD (or AUTH_PASSWORD_HASH) for a stable login.')
    log_warning('=' * 70)

if not AUTH_PASSWORD_HASH and (
    AUTH_PASSWORD.lower() in ('admin', 'password', 'changeme')
    or AUTH_PASSWORD == AUTH_USERNAME
):
    log_warning('AUTH_PASSWORD is weak or matches the username. Set a strong password before exposing the app.')

TOKEN_EXPIRE_HOURS = int(os.getenv('TOKEN_EXPIRE_HOURS')) if os.getenv('TOKEN_EXPIRE_HOURS') else 12
TOKEN_EXPIRE_HOURS = TOKEN_EXPIRE_HOURS if TOKEN_EXPIRE_HOURS > 0 else 12

JWT_SECRET_KEY = os.urandom(24).hex()

# Token scopes. Session tokens authenticate API requests; download tokens only
# authorize a single download via the /api/download?token=... URL. Keeping the
# scopes distinct prevents a download token (which can leak through URLs, proxy
# logs or browser history) from being used as a full session token.
TOKEN_SCOPE_SESSION = 'session'
TOKEN_SCOPE_DOWNLOAD = 'download'

# If not in environment docker will run as root
PUID = os.getenv('PUID', '0')
PGID = os.getenv('PGID', '0')

app.config['SECRET_KEY'] = JWT_SECRET_KEY

# Defense-in-depth headers for the SPA and API. The SPA has no inline scripts
# (Vite emits external module files), but Svelte uses inline style attributes,
# so styles still need 'unsafe-inline'. Remote cover art is proxied through
# /api/metadata/picture/preview, so the browser only loads same-origin, data:
# and blob: images.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self' data:; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes', 'on') # Debug
MUSIC_FOLDER = os.getenv('MUSIC_FOLDER', '/music')
MUSIC_ROOT = os.path.abspath(MUSIC_FOLDER)


def _env_size_mib(name, default_mib):
    """Read a positive size in MiB from the environment."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default_mib * 1024 * 1024

    try:
        value = int(raw)
    except ValueError:
        value = 0

    if value <= 0:
        log_warning(f'Invalid {name}={raw!r}; using {default_mib} MiB')
        return default_mib * 1024 * 1024
    return value * 1024 * 1024


def _format_size(size):
    """Render a byte limit as GiB or MiB for user-facing messages."""
    if size >= 1024 ** 3 and size % (1024 ** 3) == 0:
        return f'{size // (1024 ** 3)} GiB'
    return f'{size // (1024 ** 2)} MiB'


def _unique_path(path):
    """Return *path* or the first free "name (n).ext" variant."""
    base, ext = os.path.splitext(path)
    counter = 1
    candidate = path
    while os.path.exists(candidate):
        candidate = f'{base} ({counter}){ext}'
        counter += 1
    return candidate


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


def _save_upload_atomic(file_storage, destination):
    """Write an upload to a hidden temp file and move it into place.

    An interrupted client, a full disk or a killed process must never leave a
    truncated track in the library, where ``build_tree`` would list it as a
    normal file. The hidden name also keeps the temporary file out of the tree
    while the bytes are still being written.
    """
    directory = os.path.dirname(destination) or '.'
    temp_path = os.path.join(directory, f'.upload-{secrets.token_hex(8)}.part')
    stream = getattr(file_storage, 'stream', None)
    if stream is not None:
        try:
            stream.seek(0)
        except (OSError, AttributeError, ValueError):
            pass
    try:
        file_storage.save(temp_path)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# Body limits are per request. Drag-and-drop folder uploads send one request
# per file, so this caps a single file rather than the whole library.
MAX_UPLOAD_BYTES = _env_size_mib('MAX_UPLOAD_MB', 4096)
COVER_UPLOAD_BYTES = 20 * 1024 * 1024

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

# Free-space preflight leaves this much headroom in the library.
STORAGE_HEADROOM_BYTES = 256 * 1024 * 1024
COVER_UPLOAD_PATHS = frozenset({
    '/api/metadata/picture/file',
    '/api/metadata/picture/folder',
    '/api/metadata/picture/folder/current',
})

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES


@app.before_request
def limit_cover_upload_size():
    """Apply the smaller body limit to cover-art uploads."""
    if request.path in COVER_UPLOAD_PATHS:
        request.max_content_length = COVER_UPLOAD_BYTES


class AccessDenied(PermissionError):
    """A user-supplied path attempted to leave the music library."""


def _public_error_message(exc, fallback):
    """Map an exception to a short, non-sensitive message and status code.

    Exception details belong in the server log. The client only needs to know
    which category failed so it can explain the problem: permission, missing
    file, network, disk capacity, or an unexpected error.
    """
    if isinstance(exc, AccessDenied):
        return str(exc), 403
    if isinstance(exc, PermissionError):
        return 'Permission denied while accessing the library.', 403
    if isinstance(exc, FileNotFoundError):
        return 'The requested file or folder no longer exists.', 404
    if isinstance(exc, requests.exceptions.Timeout):
        return 'The external service did not respond in time.', 504
    if isinstance(exc, requests.exceptions.RequestException):
        return 'The external service request failed.', 502
    if isinstance(exc, OSError):
        if exc.errno in (errno.EACCES, errno.EPERM):
            return 'Permission denied while accessing the library.', 403
        if exc.errno == errno.ENOENT:
            return 'The requested file or folder no longer exists.', 404
        if exc.errno == errno.EISDIR:
            return 'The requested path is a folder, not a file.', 400
        if exc.errno == errno.ENOTDIR:
            return 'The requested path is not a folder.', 400
        if exc.errno == errno.EEXIST:
            return 'The destination already exists.', 409
        if exc.errno == errno.ENOSPC:
            return 'The server is out of disk space.', 500
        if exc.errno == errno.EROFS:
            return 'The filesystem is read-only.', 500
        if exc.errno in (errno.EMFILE, errno.ENFILE):
            return 'The server is temporarily unable to open more files.', 503
    return fallback, 500


def _server_error(exc, fallback='An unexpected server error occurred.', *, success=None):
    """Log the real exception and return a generic JSON error response.

    ``success`` is set for endpoints whose response schema includes it (the
    addon routes). Other routes keep the plain ``{'error': ...}`` shape.
    """
    log_error(f'{request.method} {request.path}: {exc.__class__.__name__}: {exc}')
    message, status = _public_error_message(exc, fallback)
    payload = {'error': message}
    if success is not None:
        payload['success'] = success
    return jsonify(payload), status


def _permission_error(exc):
    """Return 403 for path denials without exposing operating-system text."""
    if isinstance(exc, AccessDenied):
        return jsonify({'error': str(exc)}), 403
    log_error(f'{request.method} {request.path}: PermissionError: {exc}')
    return jsonify({'error': 'Permission denied while accessing the library.'}), 403


@app.errorhandler(500)
def handle_internal_server_error(error):
    """Return JSON for unhandled errors instead of Flask's HTML page."""
    original = getattr(error, 'original_exception', None)
    if original is not None:
        log_error(
            f'{request.method} {request.path}: Unhandled '
            f'{original.__class__.__name__}: {original}'
        )
    else:
        log_error(f'{request.method} {request.path}: Unhandled server error')
    message, status = _public_error_message(
        original,
        'An unexpected server error occurred.',
    )
    return jsonify({'error': message}), status


@app.errorhandler(413)
def handle_request_too_large(error):
    """Return JSON for oversized request bodies instead of an HTML page."""
    if request.path in COVER_UPLOAD_PATHS:
        limit = COVER_UPLOAD_BYTES
        message = f'The image is too large. The maximum size is {_format_size(limit)}.'
    elif request.path == '/api/upload':
        limit = MAX_UPLOAD_BYTES
        message = f'The uploaded file is too large. The maximum size is {_format_size(limit)}.'
    else:
        limit = MAX_UPLOAD_BYTES
        message = f'The request is too large. The maximum size is {_format_size(limit)}.'

    log_warning(
        f'{request.method} {request.path}: body exceeded {_format_size(limit)}'
    )
    return jsonify({'error': message}), 413

log_info(f'Debug set to {DEBUG}')
log_info(f'PUID set to {PUID}')
log_info(f'PGID set to {PGID}')

log_info(f'Music folder: {Path(MUSIC_FOLDER).absolute()}')
log_info(f'Log folder:{Path(LOG_DIR).absolute()}')
log_info(
    f'Upload limit: {_format_size(MAX_UPLOAD_BYTES)} per request; '
    f'cover images: {_format_size(COVER_UPLOAD_BYTES)}'
)

# ------------------------ADDONS------------------------ #

plugin_manager = PluginManager()
plugin_manager.discover_plugins()

# ---------------------VERSION CHECK---------------------#

APP_VERSION = 'v1.0.5'
# Commit the image was built from, set at build time (see Dockerfile). Lets
# users compare a running container against the build-provenance attestation.
APP_GIT_SHA = os.getenv('APP_GIT_SHA', 'unknown')
GITHUB_REPO_OWNER = 'Jonny-Ponny'
GITHUB_REPO_NAME = 'metadata-docker'

CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', '3600'))
CACHE_TTL_SECONDS = CACHE_TTL_SECONDS if CACHE_TTL_SECONDS > 0 else 3600

DISABLE_VERSION_CHECK = os.getenv('DISABLE_VERSION_CHECK', 'False').lower() in ('true', '1', 'yes', 'on')

# Cache for version info
_version_cache = {
    'latest': None,
    'update_available': False,
    'timestamp': 0
}

def _compare_versions(current: str, pulled: str) -> bool:
    """Return True if pulled version is newer than current."""
    # Strip 'v' or 'V' and split by '.'
    curr_parts = [int(x) for x in current.lower().lstrip('v').split('.')]
    pull_parts = [int(x) for x in pulled.lower().lstrip('v').split('.')]
    return pull_parts > curr_parts

def get_version_info():
    """Return current and latest version info, refreshing cache if stale."""
    global _version_cache

    # If version check is disabled, return base info without fetching
    if DISABLE_VERSION_CHECK:
        return {
            'current': APP_VERSION,
            'latest': None,
            'update_available': False
        }

    now = time.time()
    # Return cached data if still fresh
    if _version_cache['timestamp'] and (now - _version_cache['timestamp'] < CACHE_TTL_SECONDS):
        return {
            'current': APP_VERSION,
            'latest': _version_cache['latest'],
            'update_available': _version_cache['update_available']
        }

    # Cache expired or empty – fetch from GitHub
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest = data.get('tag_name', '')
            if latest:
                update_available = _compare_versions(APP_VERSION, latest)
                _version_cache = {
                    'latest': latest,
                    'update_available': update_available,
                    'timestamp': now
                }
                if update_available:
                    log_info('Version: Update available, check GitHub for more info')
                else:
                    log_info('Version: Up to date')
            else:
                log_warning("GitHub release tag_name is empty")
                _version_cache['timestamp'] = now
                return {
                    'current': APP_VERSION,
                    'latest': _version_cache.get('latest'),
                    'update_available': False
                }
        else:
            log_warning(f"GitHub API returned {response.status_code}")
            _version_cache['timestamp'] = now
            return {
                'current': APP_VERSION,
                'latest': _version_cache.get('latest'),
                'update_available': False
            }
    except Exception as e:
        log_error(f"Failed to check for updates: {e}")
        _version_cache['timestamp'] = now
        return {
            'current': APP_VERSION,
            'latest': _version_cache.get('latest'),
            'update_available': False
        }

    return {
        'current': APP_VERSION,
        'latest': _version_cache['latest'],
        'update_available': _version_cache['update_available']
    }

get_version_info()

@app.route('/api/version', methods=['GET'])
def get_version():
    info = get_version_info()
    return jsonify({
        'current_version': info['current'],
        'latest_version': info['latest'],
        'update_available': info['update_available'],
        'git_sha': APP_GIT_SHA,
        # Lets the upload UI reject an oversized file before sending it.
        'max_upload_bytes': MAX_UPLOAD_BYTES
    })

# -------------------------AUTH------------------------- #

# Token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # Decode token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            # Only session tokens may authenticate API requests. Download
            # tokens (scope 'download') must be rejected here.
            if data.get('scope') != TOKEN_SCOPE_SESSION:
                raise Exception('Not a session token')
            current_user = data.get('username')
            if not current_user or current_user != AUTH_USERNAME:
                raise Exception('Invalid user')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except Exception:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

# GET /api/validate
# Simple endpoint to check if token is valid
@app.route('/api/validate', methods=['GET'])
@token_required
def validate_token():
    """Simple endpoint to check if token is valid."""
    return jsonify({'valid': True})

# -------------------------LOGIN RATE LIMIT------------------------- #

# In-memory per-IP limiter. The container runs a single gunicorn worker, so
# this is shared by all threads. It resets on restart, which is acceptable for
# a single-admin app; a multi-worker deployment would need shared storage.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
_login_failures = {}
_login_failures_lock = threading.Lock()


def _constant_time_eq(value, expected):
    """Compare two strings without leaking content or length through timing."""
    return hmac.compare_digest(value.encode('utf-8'), expected.encode('utf-8'))


def _password_matches(password):
    if AUTH_PASSWORD_HASH:
        try:
            return check_password_hash(AUTH_PASSWORD_HASH, password)
        except (ValueError, TypeError):
            # Startup validation should prevent this, but never turn a bad
            # configuration into a 500 on the login endpoint.
            return False
    return _constant_time_eq(password, AUTH_PASSWORD)


def _client_ip():
    # Behind a reverse proxy this is the proxy's address unless a trusted
    # proxy header is configured, so the limiter remains a global limit there.
    return request.remote_addr or 'unknown'


def _login_retry_after(ip):
    """Return seconds until this IP may try again, or 0 if it may try now."""
    now = time.time()
    with _login_failures_lock:
        entry = _login_failures.get(ip)
        if not entry:
            return 0
        if entry['locked_until'] > now:
            return max(1, int(entry['locked_until'] - now + 0.999))
        if now - entry['first'] >= LOGIN_LOCKOUT_SECONDS:
            _login_failures.pop(ip, None)
        return 0


def _record_login_failure(ip):
    """Record a failed attempt and return retry-after seconds when locked."""
    now = time.time()
    with _login_failures_lock:
        entry = _login_failures.get(ip)
        if not entry or now - entry['first'] >= LOGIN_LOCKOUT_SECONDS:
            entry = {'count': 0, 'first': now, 'locked_until': 0}

        entry['count'] += 1
        retry_after = 0
        if entry['count'] >= LOGIN_MAX_ATTEMPTS:
            entry['locked_until'] = now + LOGIN_LOCKOUT_SECONDS
            retry_after = LOGIN_LOCKOUT_SECONDS
        _login_failures[ip] = entry

        # Keep the table bounded if many client addresses are seen.
        if len(_login_failures) > 4096:
            stale = [
                key for key, value in _login_failures.items()
                if value['locked_until'] <= now
                and now - value['first'] >= LOGIN_LOCKOUT_SECONDS
            ]
            for key in stale:
                _login_failures.pop(key, None)

    return retry_after


def _clear_login_failures(ip):
    with _login_failures_lock:
        _login_failures.pop(ip, None)


def _rate_limited_response(retry_after):
    response = jsonify({'error': 'Too many failed login attempts. Try again later.'})
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


# Login endpoint
@app.route('/api/login', methods=['POST'])
def login():
    client_ip = _client_ip()
    retry_after = _login_retry_after(client_ip)
    if retry_after:
        return _rate_limited_response(retry_after)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Username and password required'}), 400

    username = data.get('username')
    password = data.get('password')

    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if len(username) > 256 or len(password) > 4096:
        return jsonify({'error': 'Invalid credentials'}), 401

    username_ok = _constant_time_eq(username, AUTH_USERNAME)
    password_ok = _password_matches(password)

    if not (username_ok and password_ok):
        retry_after = _record_login_failure(client_ip)
        if retry_after:
            return _rate_limited_response(retry_after)
        return jsonify({'error': 'Invalid credentials'}), 401

    _clear_login_failures(client_ip)

    # Generate token with configurable expiry
    token = jwt.encode({
        'username': AUTH_USERNAME,
        'scope': TOKEN_SCOPE_SESSION,
        'exp': datetime.datetime.now() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'success': True,
        'token': token,
        'username': AUTH_USERNAME,
        'expires_in': TOKEN_EXPIRE_HOURS * 3600  # in seconds
    })

# Sort filetree
def natural_key(text):
    """Convert text into a list of strings and numbers for natural sorting."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text)]

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
            if os.path.isdir(full):
                # Symlinked directories are skipped: following them can escape
                # MUSIC_ROOT or recurse forever through a cycle. safe_path()
                # resolves symlinks as well, so anything not listed here could
                # not be opened through the API either.
                if os.path.islink(full):
                    continue
                children = build_tree(full, rel)
                stat = os.stat(full)
                items.append({
                    'name': entry,
                    'type': 'directory',
                    'path': rel,
                    'children': children,
                    'created': stat.st_ctime,
                    'modified': stat.st_mtime,
                    'size': 0
                })
            elif os.path.isfile(full):
                # A symlinked file is only listed when it resolves inside the
                # library. This also avoids calling os.stat() on a link that
                # points at an arbitrary outside file.
                if os.path.islink(full) and not _is_within(MUSIC_ROOT, full):
                    continue
                # Check for audio files
                if is_supported_audio(entry):
                    stat = os.stat(full)
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'audio',
                        'path': rel,
                        'size': stat.st_size,
                        'created': stat.st_ctime,
                        'modified': stat.st_mtime
                    })
                # Check for image files
                elif entry.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                    stat = os.stat(full)
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'image',
                        'path': rel,
                        'size': stat.st_size,
                        'created': stat.st_ctime,
                        'modified': stat.st_mtime
                    })

                elif entry.lower().endswith(('.txt', '.lrc')):
                    stat = os.stat(full)
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'text',
                        'path': rel,
                        'size': stat.st_size,
                        'created': stat.st_ctime,
                        'modified': stat.st_mtime
                    })
                # Everything else is still listed so it can be inspected,
                # renamed, downloaded or deleted. The metadata endpoint marks
                # these files read-only.
                else:
                    stat = os.stat(full)
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'other',
                        'path': rel,
                        'size': stat.st_size,
                        'created': stat.st_ctime,
                        'modified': stat.st_mtime
                    })
        
    except PermissionError:
        pass

    return items

def _is_within(base_path, candidate_path):
    """Return True when *candidate_path* is *base_path* or lives below it.

    Both paths are resolved with ``realpath`` first, so a symlink cannot be
    used to point outside *base_path*. ``commonpath`` is used instead of
    ``startswith`` so a sibling such as ``/music-other`` is not treated as
    being inside ``/music``.
    """
    try:
        base = os.path.realpath(base_path)
        candidate = os.path.realpath(candidate_path)
        return os.path.commonpath([base, candidate]) == base
    except ValueError:
        # Different drives on Windows cannot share a common path.
        return False


def _is_library_root(path):
    """Return True when *path* resolves to the music library root itself.

    ``safe_path()`` maps ``""``, ``"."`` and ``"/"`` to the root. Removing that
    tree, or deriving a sibling name from it, would act outside the library.
    """
    try:
        return os.path.realpath(path) == os.path.realpath(MUSIC_ROOT)
    except (OSError, ValueError):
        return False


def _generated_rename_path(parent, name):
    """Validate a generated rename target and return its full path.

    Smart rename builds names from tag values, so the result is not a
    user-typed filename. Reject empty names, ``.``/``..``, separators and
    names that would resolve outside the music library.
    """
    if not isinstance(name, str) or not name or '\0' in name:
        raise ValueError('Invalid generated name')
    if name in ('.', '..') or name.strip() != name:
        raise ValueError('Invalid generated name')
    if os.path.isabs(name) or '/' in name or '\\' in name:
        raise ValueError('Invalid generated name')

    new_path = os.path.join(parent, name)
    if not _is_within(MUSIC_ROOT, new_path):
        raise ValueError('Invalid generated name')
    return new_path


def safe_path(file_path):
    """Resolve a user-supplied path and keep it inside the music folder.

    Leading slashes are ignored so both ``/album/song.mp3`` and
    ``album/song.mp3`` refer to the library root. Symlinks are resolved for
    the containment check, so a link inside the library cannot point outside
    it. Raises ``PermissionError`` when the resolved path would escape
    ``MUSIC_FOLDER``.
    """
    if not MUSIC_FOLDER:
        return file_path

    if file_path is None or '\0' in str(file_path):
        raise AccessDenied('Invalid path.')

    full_path = os.path.abspath(
        os.path.join(MUSIC_ROOT, str(file_path).lstrip('/'))
    )
    if not _is_within(MUSIC_ROOT, full_path):
        raise AccessDenied('Path is outside the music library.')
    return full_path

# -------------------------API ENDPOINTS------------------------- #

# GET /api/ping
# Health check endpoint
@app.route('/api/ping', methods=['GET'])
def health():
    try:
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception:
        return jsonify({"status": "error"}), 500

# GET /api/files
# Fetch library structure as filetree
@app.route('/api/files', methods=['GET'])
@token_required
def list_files():
    try:
        tree = build_tree(MUSIC_FOLDER, '')
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
    data = request.get_json()
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
    data = request.get_json()
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

    os.makedirs(target_dir, exist_ok=True)

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

    incoming_size = _stream_size(file)

    # Resolve duplicate names according to the conflict policy. Comparing the
    # size makes re-dropping an unchanged folder a no-op instead of producing
    # "name (1).ext" copies.
    skipped = False
    renamed = False
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            return jsonify({'error': 'A folder with that name already exists'}), 400

        same_size = (
            incoming_size is not None
            and os.path.isfile(file_path)
            and os.path.getsize(file_path) == incoming_size
        )
        if conflict == UPLOAD_CONFLICT_SKIP_IDENTICAL and same_size:
            skipped = True
        else:
            new_path = _unique_path(file_path)
            renamed = new_path != file_path
            file_path = new_path

    rel_path = os.path.relpath(file_path, MUSIC_FOLDER).replace('\\', '/')

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

    try:
        _save_upload_atomic(file, file_path)

        log_info(f"Successfully uploaded {file_path}")
        
        return jsonify({
            'success': True,
            'skipped': False,
            'renamed': renamed,
            'path': rel_path,  # Normalize path separators
            'filename': os.path.basename(file_path),
            'original_filename': original_filename
        })
    except Exception as e:
        return _server_error(e)

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
    data = request.get_json(silent=True) or {}
    desired_path = data.get('path', '')
    conflict = (data.get('conflict') or DEFAULT_MKDIR_CONFLICT).strip()
    if not desired_path:
        return jsonify({'error': 'No path provided'}), 400
    if conflict not in MKDIR_CONFLICTS:
        return jsonify({'error': 'Invalid conflict policy'}), 400

    try:
        full_path = safe_path(desired_path)

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

        rel_path = os.path.relpath(full_path, MUSIC_FOLDER).replace('\\', '/')

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
    data = request.get_json()
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

        os.rename(full_old, full_new)

        log_info(f"Renamed {full_old} to {full_new}")

        # Return the new relative path
        new_rel = os.path.relpath(full_new, MUSIC_FOLDER).replace('\\', '/')
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
    data = request.get_json()
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
    data = request.get_json()
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
            dest_full = MUSIC_FOLDER

        # New full path: destination + basename of source
        new_full = os.path.join(dest_full, os.path.basename(source_full))

        # Prevent directory traversal
        if not _is_within(MUSIC_ROOT, new_full):
            return jsonify({'error': 'Invalid destination'}), 400

        # If source is a directory, ensure destination is not inside source
        if os.path.isdir(source_full):
            if new_full.startswith(source_full + os.sep):
                return jsonify({'error': 'Cannot move a folder into its own subfolder'}), 400

        # Handle name conflict
        if os.path.exists(new_full):
            return jsonify({'error': 'An item with that name already exists in the destination'}), 409

        # Perform the move
        shutil.move(source_full, new_full)

        log_info(f"Moved {source_full} to {new_full}")

        # Return the new relative path
        new_rel = os.path.relpath(new_full, MUSIC_FOLDER).replace('\\', '/')
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
    data = request.get_json()
    path = data.get('path')

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    try:
        full_path = safe_path(path)
        if not os.path.exists(full_path):
            return jsonify({'error': 'Path not found'}), 404

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
                'picture': metadata.get('picture')
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
    data = request.get_json() or {}
    image_url = data.get('url')
    file_path = data.get('path')
    
    if not image_url or not file_path:
        return jsonify({'error': 'Missing url or path parameter'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
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
                'picture': metadata.get('picture')
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
        full_path = safe_path(folder_path) if folder_path else MUSIC_FOLDER
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
    data = request.get_json()
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
        full_path = safe_path(folder_path) if folder_path else MUSIC_FOLDER
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
    data = request.get_json()
    path = data.get('path')
    field = data.get('field')
    recursive = data.get('recursive', False)  # Add recursive flag
    
    if not path or not field:
        return jsonify({'error': 'Missing path or field'}), 400
    
    try:
        full_path = safe_path(path)
        
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
    data = request.get_json()
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
                'picture': metadata.get('picture')
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
        
        # Determine mimetype
        ext = os.path.splitext(full_path)[1].lower()
        mimetypes = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        mimetype = mimetypes.get(ext, 'application/octet-stream')
        
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
    data = request.get_json()
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
        
        if not metadata.get('picture'):
            return jsonify({'error': 'No cover art found in file'}), 404
        
        # Extract image data from base64
        picture_data = metadata['picture']
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
            'path': os.path.relpath(output_path, MUSIC_FOLDER).replace('\\', '/')
        })
        
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# GET /api/logs
# Get log entries with filtering options
@app.route('/api/logs', methods=['GET'])
@token_required
def get_logs():
    """Get log entries with filtering options"""
    try:
        # Get query parameters
        lines = request.args.get('lines', default=100, type=int)
        level = request.args.get('level', default=None, type=str)
        search = request.args.get('search', default=None, type=str)
        
        log_file = LOG_DIR / "app.log"
        
        if not log_file.exists():
            return jsonify({
                "logs": [],
                "total": 0,
                "message": "No logs found"
            })
        
        # Read log file
        with open(log_file, 'r', encoding='utf-8') as f:
            all_logs = f.readlines()
        
        # Filter by level if specified
        if level:
            # Match the pattern [LEVEL] in the log
            level_pattern = f"[{level.upper()}]"
            all_logs = [log for log in all_logs if level_pattern in log]
        
        # Filter by search term if specified
        if search:
            all_logs = [log for log in all_logs if search.lower() in log.lower()]
        
        # Get last N lines (most recent)
        recent_logs = all_logs[-lines:]
        
        # Parse logs into structured format
        parsed_logs = []
        for log in recent_logs:
            # Parse timestamp, level, and message from format: [2024-01-01 12:34:56] [INFO] message
            log_line = log.strip()
            
            # Try to match the pattern [timestamp] [level] message
            match = re.match(r'\[(.*?)\] \[(.*?)\] (.*)', log_line)
            
            if match:
                parsed_logs.append({
                    'timestamp': match.group(1),
                    'level': match.group(2),
                    'message': match.group(3)
                })
            else:
                parsed_logs.append({'raw': log_line})
        
        return jsonify({
            "logs": parsed_logs,
            "total": len(all_logs),
            "displayed": len(recent_logs),
            "filters": {
                "level": level,
                "search": search
            }
        })
        
    except Exception as e:
        return _server_error(e, 'Could not read the logs.')


# POST /api/logs/clear
# Clear all logs
@app.route('/api/logs/clear', methods=['POST'])
@token_required
def clear_logs():
    """Clear all logs"""
    try:
        log_file = LOG_DIR / "app.log"
        if log_file.exists():
            log_file.write_text("")
            log_info("Logs cleared by user")
        return jsonify({"message": "Logs cleared successfully"})
    except Exception as e:
        return _server_error(e, 'Could not clear the logs.')


# POST /api/apply-renaming-scheme
# Apply renaming scheme to folder or file
@app.route('/api/apply-renaming-scheme', methods=['POST'])
@token_required
def apply_renaming_scheme():
    """Apply a renaming scheme to a folder or file."""
    data = request.get_json()
    path = data.get('path')
    scheme = data.get('scheme')
    is_folder = data.get('isFolder', True)
    replace_spaces = data.get('replaceSpaces', False)
    
    if not path or not scheme:
        return jsonify({'error': 'Missing path or scheme'}), 400
    
    try:
        full_path = safe_path(path)
        
        # Allowed variables mapping to metadata fields
        variable_map = {
            'TITLE': 'title',
            'ALBUM': 'album',
            'ARTIST': 'artist',
            'ALBUMARTIST': 'albumArtist',
            'YYYY': 'date',  # Will extract just the year from date
            'TRACK': 'trackNumber',
            'DISK': 'diskNumber',
            'RELEASETYPE': 'releaseType',
        }

        def extract_year_regex(date_val):
            if not date_val:
                return None
            
            # Matches a 4-digit year (1800-2099) bounded by non-digit characters
            match = re.search(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)', str(date_val))
            return match.group(0) if match else None
        
        def generate_name_from_scheme(scheme_str, metadata):
            """Generate new name from scheme and metadata."""
            result = scheme_str
            
            # First, check if all variables in the scheme have values
            variables_in_scheme = re.findall(r'\[([^\[\]]+)\]', scheme_str)
            
            # Process date value once
            extracted_year = extract_year_regex(metadata.get('date'))
            
            missing_fields = []
            for var in variables_in_scheme:
                if var not in variable_map:
                    continue  # Skip unknown variables (they'll remain as-is)
                
                field = variable_map[var]
                
                if field == 'date':
                    has_value = extracted_year is not None
                else:
                    has_value = bool(metadata.get(field))
                
                if not has_value:
                    missing_fields.append(var)
            
            if missing_fields:
                raise ValueError(f"Missing metadata fields for variables: {', '.join(missing_fields)}. Please fill these fields first.")
            
            # Replace each variable with its value
            for var, field in variable_map.items():
                value = ''
                if field == 'date':
                    value = extracted_year or ''
                elif field == 'trackNumber' and metadata.get('trackNumber'):
                    track = str(metadata['trackNumber']).split('/')[0]
                    value = track.zfill(2)
                elif field == 'diskNumber' and metadata.get('diskNumber'):
                    disk = str(metadata['diskNumber']).split('/')[0]
                    value = disk.zfill(2)
                elif field == 'releaseType' and metadata.get('releaseType'):
                    value = str(metadata['releaseType'])
                elif metadata.get(field):
                    value = str(metadata[field])
                
                # Replace the variable (case sensitive)
                result = result.replace(f'[{var}]', value)
            
            # Clean up multiple spaces and trim
            result = re.sub(r'\s+', ' ', result).strip()
            
            # Replace spaces with underscores if option is enabled
            if replace_spaces:
                result = result.replace(' ', '_')
            
            # Remove any characters that aren't allowed in filenames
            result = re.sub(r'[<>:"/\\|?*]', '', result)
            
            return result

        def _same_path(path1, path2):
            if os.path.abspath(path1) == os.path.abspath(path2):
                return True
            try:
                return os.path.exists(path1) and os.path.exists(path2) and os.path.samefile(path1, path2)
            except OSError:
                return False
        
        if is_folder:
            # Handle folder rename
            if not os.path.isdir(full_path):
                return jsonify({'error': 'Folder not found'}), 404
            
            # Find first audio file in folder to extract metadata. Symlinks are
            # skipped so a bulk rename never reads a target outside the folder.
            first_audio = None
            for root, dirs, files in os.walk(full_path):
                dirs[:] = [
                    name for name in dirs
                    if not os.path.islink(os.path.join(root, name))
                ]
                for file in sorted(files):
                    candidate = os.path.join(root, file)
                    if os.path.islink(candidate):
                        continue
                    if is_supported_audio(file):
                        first_audio = candidate
                        break
                if first_audio:
                    break
            
            if not first_audio:
                return jsonify({'error': 'No audio files found in folder to extract metadata'}), 400
            
            # Extract metadata from first file
            metadata = extract_metadata(first_audio)
            
            try:
                # Generate new folder name (this will raise ValueError if fields are missing)
                new_name = generate_name_from_scheme(scheme, metadata)
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
            if _same_path(new_path, full_path):
                return jsonify({
                    'success': True,
                    'newPath': os.path.relpath(full_path, MUSIC_FOLDER).replace('\\', '/'),
                    'newName': os.path.basename(full_path)
                })
            
            # Handle duplicates
            if os.path.exists(new_path):
                base = new_path
                counter = 1
                while os.path.exists(new_path):
                    new_path = f'{base} ({counter})'
                    counter += 1
            
            if not _is_within(MUSIC_ROOT, new_path):
                return jsonify({'error': 'Invalid generated name'}), 400
            os.rename(full_path, new_path)
            
            log_info(f"Smart renamed folder {full_path} to {new_path}")
            
            return jsonify({
                'success': True,
                'newPath': os.path.relpath(new_path, MUSIC_FOLDER).replace('\\', '/'),
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
            
            try:
                # Generate new file name (this will raise ValueError if fields are missing)
                new_name_without_ext = generate_name_from_scheme(scheme, metadata)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            
            if not new_name_without_ext:
                return jsonify({'error': 'Generated name is empty'}), 400
            if new_name_without_ext in ('.', '..'):
                return jsonify({'error': 'Invalid generated name'}), 400
            
            # Add original extension
            ext = os.path.splitext(full_path)[1]
            new_name = new_name_without_ext + ext
            
            # Rename file. The generated name is validated as a bare filename
            # and the destination must stay inside the library.
            parent = os.path.dirname(full_path)
            try:
                new_path = _generated_rename_path(parent, new_name)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

            # If it already matches the scheme, do not rename
            if _same_path(new_path, full_path):
                return jsonify({
                    'success': True,
                    'newPath': os.path.relpath(full_path, MUSIC_FOLDER).replace('\\', '/'),
                    'newName': os.path.basename(full_path)
                })

            # Handle duplicates
            if os.path.exists(new_path):
                base, ext = os.path.splitext(new_path)
                counter = 1
                while os.path.exists(new_path):
                    new_path = f'{base} ({counter}){ext}'
                    counter += 1

            if not _is_within(MUSIC_ROOT, new_path):
                return jsonify({'error': 'Invalid generated name'}), 400
            os.rename(full_path, new_path)
            
            log_info(f"Smart renamed file {full_path} to {new_path}")
            
            return jsonify({
                'success': True,
                'newPath': os.path.relpath(new_path, MUSIC_FOLDER).replace('\\', '/'),
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
    data = request.get_json(silent=True) or {}
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
    data = request.get_json(silent=True) or {}
    path = data.get('path')
    is_folder = data.get('isFolder', False)

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    return _send_download(path, bool(is_folder))


# Read text file content
# GET /api/text?path=<file_path>
@app.route('/api/text', methods=['GET'])
@token_required
def get_text_file():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400

    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        # Restrict to text files
        if not full_path.lower().endswith(('.txt', '.lrc')):
            return jsonify({'error': 'Not a text file'}), 400

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({'content': content})

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# Write to text file
# POST /api/text/save
@app.route('/api/text/save', methods=['POST'])
@token_required
def save_text_file():
    data = request.get_json()
    file_path = data.get('path')
    content = data.get('content')

    if not file_path or content is None:
        return jsonify({'error': 'Missing path or content'}), 400

    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        if not full_path.lower().endswith(('.txt', '.lrc')):
            return jsonify({'error': 'Not a text file'}), 400

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        log_info(f"Updated text file: {full_path}")
        return jsonify({'success': True})

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)



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
    if parsed.scheme not in ('http', 'https'):
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
    limit = request.args.get('limit', 5, type=int)

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
    limit = request.args.get('limit', 5, type=int)

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