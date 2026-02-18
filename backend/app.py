import os
import shutil
from metadata_extractor import *
from metadata_writer import *

from flask import Flask, jsonify, request, send_file, abort, send_from_directory

app = Flask(__name__, static_folder='static', static_url_path='')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes', 'on') # Debug
PORT = int(os.getenv('CONTAINER_PORT', 5000))                            # Container port
HOST_PORT = os.getenv('HOST_PORT')                                       # Host port, only for info
MUSIC_FOLDER = '/music'

print('\n')
print('==============================================================================================')
print('\n')

print(f'Debug set to {DEBUG}')
print(f'Host port set to {HOST_PORT}')
print(f'Container port set to {PORT}')

def build_tree(current_path, relative_path):
    items = []
    try:
        for entry in os.listdir(current_path):
            full = os.path.join(current_path, entry)
            # Normalize to forward slashes
            rel = os.path.join(relative_path, entry).replace('\\', '/')
            if os.path.isdir(full):
                children = build_tree(full, rel)
                # Get directory stats
                stat = os.stat(full)
                items.append({
                    'name': entry,
                    'type': 'directory',
                    'path': rel,
                    'children': children,
                    'created': stat.st_ctime,  # Creation time
                    'modified': stat.st_mtime,  # Modified time
                    'size': 0  # Directories size as 0 for sorting
                })
            elif os.path.isfile(full) and entry.lower().endswith(('.mp3', '.flac')):
                stat = os.stat(full)
                items.append({
                    'name': entry,
                    'type': 'file',
                    'path': rel,
                    'size': stat.st_size,
                    'created': stat.st_ctime,
                    'modified': stat.st_mtime
                })
        
    except PermissionError:
        pass  # skip folders we can't read

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

@app.route('/api/audio')
def serve_audio():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    try:
        full_path = safe_path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        print(f'Serving audio: {full_path}')
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
        file_path = f'{name} ({counter}){ext}'
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
        return jsonify({'success': True, 'path': rel_path})

    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
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

# Endpoint to move files/folders    
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

        # Return the new relative path
        new_rel = os.path.relpath(new_full, MUSIC_FOLDER).replace('\\', '/')
        return jsonify({'success': True, 'newPath': new_rel})

    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# Endpoint to copy files/folders
@app.route('/api/copy', methods=['POST'])
def copy_item():
    """Delete a file or folder."""
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

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

# Endpoint to delete specific field
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

# Endpoint to delete cover art
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
    
# Serve Svelte frontend
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)