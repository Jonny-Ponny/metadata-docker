import os
from metadata_extractor import *
from flask import Flask, jsonify, request

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)