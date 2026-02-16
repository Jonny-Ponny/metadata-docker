import os

from flask import Flask, jsonify

MUSIC_FOLDER = '/music'
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes', 'on')

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



# -------------------------API ENDPOINTS------------------------- #

@app.route('/api/files')
def list_files():
    try:
        tree = build_tree(MUSIC_FOLDER, '')
        return jsonify(tree)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)