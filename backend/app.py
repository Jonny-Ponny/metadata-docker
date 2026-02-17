import os
import shutil
from metadata_extractor import *
from flask import Flask, jsonify, request, send_file, abort

# MUSIC_FOLDER = '/music'
MUSIC_FOLDER = 'D:\\Music' # Development

PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes', 'on')

app = Flask(__name__, static_folder='static', static_url_path='')

def build_tree(current_path, relative_path):
    items = []
    try:
        for entry in os.listdir(current_path):
            full = os.path.join(current_path, entry)
            rel = os.path.join(relative_path, entry) if relative_path else entry
            if os.path.isdir(full):
                children = build_tree(full, rel)
                items.append({
                    'name': entry,
                    'type': 'directory',
                    'path': rel,
                    'children': children
                })
            elif os.path.isfile(full) and entry.lower().endswith(('.mp3', '.flac')):
                items.append({
                    'name': entry,
                    'type': 'file',
                    'path': rel,
                    'size': os.path.getsize(full)
                })
        
        items.sort(key=lambda x: x['name'].lower())
    except PermissionError:
        pass  # skip folders we can't read

    return items

def safe_path(file_path):
    """Resolve and validate path against BASE_DIR if configured."""
    if MUSIC_FOLDER:
        full_path = os.path.abspath(os.path.join(MUSIC_FOLDER, file_path.lstrip('/')))
        if not full_path.startswith(MUSIC_FOLDER):
            raise PermissionError("Access denied: path outside base directory")
        return full_path
    return file_path

# -------------------------API ENDPOINTS------------------------- #

@app.route('/api/files')
def list_files():
    try:
        tree = build_tree(MUSIC_FOLDER, '')
        return jsonify(tree)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# GET /api/metadata?path=<file_path>
# Fetch all metadata for a specific file.

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

# POST /api/metadata/folder
# Update a single metadata field for all files in a folder

@app.route('/api/audio')
def serve_audio():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        print(f"Serving audio: {full_path}")
        # Set correct MIME type based on file extension
        mimetype = 'audio/mpeg' if full_path.lower().endswith('.mp3') else 'audio/flac'
        return send_file(full_path, mimetype=mimetype, conditional=True)
    
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
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
    
    # Regular file upload - PRESERVE ORIGINAL FILENAME
    # Don't use secure_filename if you want to preserve special characters
    # Instead, sanitize only path separators and null bytes
    filename = original_filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    
    # Build the full file path
    file_path = os.path.join(target_dir, filename)
    
    # Handle duplicate filenames
    counter = 1
    original_path = file_path
    while os.path.exists(file_path):
        name, ext = os.path.splitext(original_path)
        file_path = f"{name} ({counter}){ext}"
        counter += 1
    
    try:
        file.save(file_path)
        
        # Get relative path for response
        rel_path = os.path.relpath(file_path, MUSIC_FOLDER)
        
        return jsonify({
            'success': True,
            'path': rel_path.replace('\\', '/'),  # Normalize path separators
            'filename': os.path.basename(file_path),
            'original_filename': original_filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to create directories
@app.route('/api/mkdir', methods=['POST'])
def create_directory():
    """Create a new directory"""
    data = request.get_json()
    dir_path = data.get('path', '')
    
    if not dir_path:
        return jsonify({'error': 'No path provided'}), 400
    
    try:
        full_path = safe_path(dir_path)
        os.makedirs(full_path, exist_ok=True)
        return jsonify({'success': True, 'path': dir_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# Endpoint to rename files/folders
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

        # Return the new relative path
        new_rel = os.path.relpath(full_new, MUSIC_FOLDER).replace('\\', '/')
        return jsonify({'success': True, 'newPath': new_rel})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to delete files/folders
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
        else:
            shutil.rmtree(full_path)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)