import os
import shutil
import re
import jwt
import datetime
from functools import wraps
from metadata_extractor import *
from metadata_writer import *
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from logger_config import log_info, log_error, log_warning, LOG_DIR

log_info("STARTING")
app = Flask(__name__, static_folder='static', static_url_path='')

# Auth config from environment (with defaults)
if os.getenv('AUTH_USERNAME'):
    AUTH_USERNAME = os.getenv('AUTH_USERNAME')
else:
    AUTH_USERNAME = 'admin'
    log_warning('AUTH_USERNAME not in environment, using default')
if os.getenv('AUTH_PASSWORD'):
    AUTH_PASSWORD = os.getenv('AUTH_PASSWORD')
else:
    AUTH_PASSWORD = 'admin'
    log_warning('AUTH_PASSWORD not in environment, using default')

TOKEN_EXPIRE_HOURS = int(os.getenv('TOKEN_EXPIRE_HOURS')) if os.getenv('TOKEN_EXPIRE_HOURS') else 24
TOKEN_EXPIRE_HOURS = TOKEN_EXPIRE_HOURS if TOKEN_EXPIRE_HOURS > 0 else 24

JWT_SECRET_KEY = os.urandom(24).hex()

# If not in environment docker will run as root
PUID = os.getenv('PUID', '0')
PGID = os.getenv('PGID', '0')

app.config['SECRET_KEY'] = JWT_SECRET_KEY

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes', 'on') # Debug
MUSIC_FOLDER = '/music'

log_info(f'Debug set to {DEBUG}')
log_info(f'PUID set to {PUID}')
log_info(f'PUID set to {PGID}')

log_info(f'Music folder: {Path(MUSIC_FOLDER).absolute()}')
log_info(f'Log folder:{Path(LOG_DIR).absolute()}')

log_info(f'Login: {AUTH_USERNAME}')
log_info(f'Password: {AUTH_PASSWORD}')

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
            current_user = data.get('username')
            if not current_user or current_user != AUTH_USERNAME:
                raise Exception('Invalid user')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except Exception as e:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

# Login endpoint with plain text check
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    username = data.get('username')
    password = data.get('password')
    
    # Simple plain text check
    if username != AUTH_USERNAME or password != AUTH_PASSWORD:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate token with configurable expiry
    token = jwt.encode({
        'username': username,
        'exp': datetime.datetime.now() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'success': True,
        'token': token,
        'username': username,
        'expires_in': TOKEN_EXPIRE_HOURS * 3600  # in seconds
    })

def build_tree(current_path, relative_path):
    items = []
    try:
        for entry in os.listdir(current_path):
            full = os.path.join(current_path, entry)
            rel = os.path.join(relative_path, entry).replace('\\', '/')
            if os.path.isdir(full):
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
                # Check for audio files
                if entry.lower().endswith(('.mp3', '.flac')):
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
        
    except PermissionError:
        pass

    return items

def safe_path(file_path):
    """Resolve and validate path against BASE_DIR if configured."""
    if MUSIC_FOLDER:
        full_path = os.path.abspath(os.path.join(MUSIC_FOLDER, file_path.lstrip('/')))
        if not full_path.startswith(MUSIC_FOLDER):
            raise PermissionError('Access denied: path outside base directory')
        return full_path
    return file_path

# -------------------------API ENDPOINTS------------------------- #

# GET /api/files
# Fetch library structure as filetree
@token_required
@app.route('/api/files')
def list_files():
    try:
        tree = build_tree(MUSIC_FOLDER, '')
        return jsonify(tree)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/metadata?path=<file_path>
# Fetch all metadata for a specific file
@token_required
@app.route('/api/metadata')
def get_metadata():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400

    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        metadata = extract_metadata(full_path)
        if metadata is None:
            return jsonify({'error': 'Could not read metadata (unsupported format?)'}), 500

        return jsonify(metadata)

    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/file
# Update a single metadata field for one file
@token_required
@app.route('/api/metadata/file', methods=['POST'])
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
        
        # Only process mp3 and flac files
        if not (full_path.lower().endswith('.mp3') or full_path.lower().endswith('.flac')):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        success = update_file_metadata(full_path, field, value)
        if success:
            return jsonify({'success': True, 'message': f'Updated {field} for {os.path.basename(file_path)}'})
        else:
            return jsonify({'error': 'Failed to update metadata'}), 500
            
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/folder
# Update a single metadata field for all files in a folder
@token_required
@app.route('/api/metadata/folder', methods=['POST'])
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
        
        # Only process mp3 and flac files in the folder
        results = update_folder_metadata(full_path, field, value)
        
        return jsonify({
            'success': True, 
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': f"Updated {results['updated']} of {results['total']} files"
        })
            
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/audio?path=<file_path>
# Fetch audiofile
@app.route('/api/audio')
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
        # Set correct MIME type based on file extension
        mimetype = 'audio/mpeg' if full_path.lower().endswith('.mp3') else 'audio/flac'
        return send_file(full_path, mimetype=mimetype, conditional=True)
    
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    original_filename = request.form.get('originalFilename', file.filename)
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Determine target directory
    if target_path:
        # Handle nested paths (for folders)
        target_dir = os.path.join(MUSIC_FOLDER, target_path)
    else:
        target_dir = MUSIC_FOLDER
    
    # Ensure target directory exists
    os.makedirs(target_dir, exist_ok=True)
    
    # Check if this is a directory upload (multiple files with same base path)
    if hasattr(file, 'webkitRelativePath') and file.webkitRelativePath:
        # This is from a folder upload, preserve the full relative path
        rel_path = file.webkitRelativePath
        path_parts = rel_path.split('/')
        
        # Remove filename from path
        path_parts.pop()
        
        if path_parts:
            # Create subdirectories
            subdir = os.path.join(*path_parts)
            target_dir = os.path.join(target_dir, subdir)
            os.makedirs(target_dir, exist_ok=True)
    
    filename = original_filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    
    # Build the full file path
    file_path = os.path.join(target_dir, filename)
    
    # Handle duplicate filenames
    counter = 1
    original_path = file_path
    while os.path.exists(file_path):
        name, ext = os.path.splitext(original_path)
        file_path = f'{name} ({counter}){ext}'
        counter += 1
    
    try:
        file.save(file_path)
        
        # Get relative path for response
        rel_path = os.path.relpath(file_path, MUSIC_FOLDER)

        log_info(f"Successfully uploaded {file_path}")
        
        return jsonify({
            'success': True,
            'path': rel_path.replace('\\', '/'),  # Normalize path separators
            'filename': os.path.basename(file_path),
            'original_filename': original_filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/mkdir
# Create a new directory
@token_required
@app.route('/api/mkdir', methods=['POST'])
def create_directory():
    """Create a new directory. If the path already exists, generate a unique name."""
    data = request.get_json()
    desired_path = data.get('path', '')
    if not desired_path:
        return jsonify({'error': 'No path provided'}), 400

    try:
        full_path = safe_path(desired_path)
        # If it exists, append a number in parentheses until a free name is found
        if os.path.exists(full_path):
            base = full_path
            counter = 1
            while os.path.exists(full_path):
                full_path = f'{base} ({counter})'
                counter += 1

        os.makedirs(full_path, exist_ok=False)  # now it definitely doesn't exist
        rel_path = os.path.relpath(full_path, MUSIC_FOLDER).replace('\\', '/')

        log_info(f"Created new directory {full_path}")

        return jsonify({'success': True, 'path': rel_path})

    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# POST /api/rename
# Rename a file or directory
@token_required
@app.route('/api/rename', methods=['POST'])
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
        full_new = os.path.join(parent, new_name)

        # Prevent directory traversal in the new name
        if not full_new.startswith(MUSIC_FOLDER):
            return jsonify({'error': 'Invalid new name'}), 400

        os.rename(full_old, full_new)

        log_info(f"Renamed {full_old} to {full_new}")

        # Return the new relative path
        new_rel = os.path.relpath(full_new, MUSIC_FOLDER).replace('\\', '/')
        return jsonify({'success': True, 'newPath': new_rel})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/delete
# Delete a file or folder
@token_required
@app.route('/api/delete', methods=['POST'])
def delete_item():
    """Delete a file or folder."""
    data = request.get_json()
    path = data.get('path')

    if not path:
        return jsonify({'error': 'Missing path'}), 400

    try:
        full_path = safe_path(path)
        if not os.path.exists(full_path):
            return jsonify({'error': 'Path not found'}), 404

        if os.path.isfile(full_path):
            os.remove(full_path)
            log_info(f"Deleted {full_path}")
        else:
            shutil.rmtree(full_path)
            log_info(f"Deleted {full_path} and its contents")


        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/move
# Move a file or folder to a new destination folder
@token_required
@app.route('/api/move', methods=['POST'])
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
        if not new_full.startswith(MUSIC_FOLDER):
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
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# POST /api/copy
# Create a copy of file/directory
@token_required
@app.route('/api/copy', methods=['POST'])
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
            shutil.copytree(full_path, new_name)
        
        log_info(f"Created a copy of {full_path}")

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/picture/file
# Update cover art for a single file
@token_required
@app.route('/api/metadata/picture/file', methods=['POST'])
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
        
        # Only process mp3 and flac files
        if not (full_path.lower().endswith('.mp3') or full_path.lower().endswith('.flac')):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        # Read image data
        image_data = image_file.read()
        mime_type = image_file.mimetype
        
        success = update_file_picture(full_path, image_data, mime_type)
        
        if success:
            # Get updated metadata to return new picture data
            from metadata_extractor import extract_metadata
            metadata = extract_metadata(full_path)
            
            return jsonify({
                'success': True, 
                'message': f'Updated cover art for {os.path.basename(file_path)}',
                'picture': metadata.get('picture')
            })
        else:
            return jsonify({'error': 'Failed to update cover art'}), 500
            
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/picture/folder
# Update cover art for all files in a folder
@token_required
@app.route('/api/metadata/picture/folder', methods=['POST'])
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
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# POST /api/metadata/folder/current
# Update a single metadata field for all files in a folder (current folder only, no subfolders)
@token_required
@app.route('/api/metadata/folder/current', methods=['POST'])
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
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/picture/folder/current
# Update cover art for all files in a folder (current folder only, no subfolders)
@token_required
@app.route('/api/metadata/picture/folder/current', methods=['POST'])
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
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/field/delete
# Delete a specific metadata field from a file
@token_required
@app.route('/api/metadata/field/delete', methods=['POST'])
def delete_metadata_field():
    """Delete a specific metadata field from a file."""
    data = request.get_json()
    file_path = data.get('path')
    field = data.get('field')
    
    if not file_path or not field:
        return jsonify({'error': 'Missing path or field'}), 400
    
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Only process mp3 and flac files
        if not (full_path.lower().endswith('.mp3') or full_path.lower().endswith('.flac')):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        from metadata_writer import delete_metadata_field as delete_field
        success = delete_field(full_path, field)
        
        if success:
            return jsonify({'success': True, 'message': f'Deleted {field} from {os.path.basename(file_path)}'})
        else:
            return jsonify({'error': 'Failed to delete field'}), 500
            
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/picture/delete
# Delete cover art from a file
@token_required
@app.route('/api/metadata/picture/delete', methods=['POST'])
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
        
        # Only process mp3 and flac files
        if not (full_path.lower().endswith('.mp3') or full_path.lower().endswith('.flac')):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        from metadata_writer import delete_cover_art as delete_picture
        success = delete_picture(full_path)

        log_info(f"Deleted cove art from {full_path}")
        
        if success:
            # Get updated metadata to confirm deletion
            from metadata_extractor import extract_metadata
            metadata = extract_metadata(full_path)
            
            return jsonify({
                'success': True, 
                'message': f'Deleted cover art from {os.path.basename(file_path)}',
                'picture': metadata.get('picture')
            })
        else:
            return jsonify({'error': 'Failed to delete cover art'}), 500
            
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/image
# Fetch image
@token_required
@app.route('/api/image')
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
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST /api/metadata/picture/save-as-file
# Extract cover art from audio file and save as cover.jpg in the same folder
@token_required
@app.route('/api/metadata/picture/save-as-file', methods=['POST'])
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
        
        # Only process mp3 and flac files
        if not (full_path.lower().endswith('.mp3') or full_path.lower().endswith('.flac')):
            return jsonify({'error': 'Unsupported file format'}), 400
        
        from metadata_extractor import extract_metadata
        metadata = extract_metadata(full_path)
        
        if not metadata.get('picture'):
            return jsonify({'error': 'No cover art found in file'}), 404
        
        # Extract image data from base64
        import base64
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
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/logs
# Get log entries with filtering options
@token_required
@app.route('/api/logs', methods=['GET'])
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
            import re
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
        log_error(f"Error fetching logs: {str(e)}")
        return jsonify({"error": str(e)}), 500


# POST /api/logs/clear
# Clear all logs
@token_required
@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Clear all logs"""
    try:
        log_file = LOG_DIR / "app.log"
        if log_file.exists():
            log_file.write_text("")
            log_info("Logs cleared by user")
        return jsonify({"message": "Logs cleared successfully"})
    except Exception as e:
        log_error(f"Error clearing logs: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Serve Svelte frontend
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=DEBUG)