"""Tag endpoints: read and edit metadata, covers, and serve audio/images."""

import base64
import os
import re

import requests
from flask import Blueprint, Response, jsonify, request, send_file

from auth import token_required
from config import APP_VERSION, MUSIC_ROOT
from errors import (
    _json_object,
    _permission_error,
    _server_error,
)
from formats import image_mime_for, is_supported_audio, mime_for
from logger_config import log_info
from metadata_extractor import extract_metadata, read_only_metadata
from metadata_writer import (
    delete_field_from_folder,
    update_file_metadata,
    update_file_picture,
    update_folder_metadata,
    update_folder_metadata_only_current,
    update_folder_pictures,
    update_folder_pictures_only_current,
)
from paths import safe_path
from safe_fetch import ImageTooLargeError, UnsafeURLError, fetch_image

bp = Blueprint('tags', __name__)


def _path(value):
    """Resolve a user path against the library root."""
    return safe_path(value, MUSIC_ROOT)


def _update_folder_field(recursive):
    """Set one tag on every audio file in a folder, optionally recursive."""
    data, error = _json_object()
    if error:
        return error
    folder_path = data.get('path')
    field = data.get('field')
    value = data.get('value')

    if not folder_path or not field:
        return jsonify({'error': 'Missing path or field'}), 400

    try:
        full_path = _path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404

        if recursive:
            results = update_folder_metadata(full_path, field, value)
            suffix = ''
        else:
            results = update_folder_metadata_only_current(full_path, field, value)
            suffix = ' in current folder'

        return jsonify({
            'success': True,
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': f"Updated {results['updated']} of {results['total']} files{suffix}"
        })

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)


def _update_folder_cover(recursive):
    """Set the cover on every audio file in a folder, optionally recursive."""
    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    image_file = request.files['file']
    folder_path = request.form.get('path')

    if folder_path is None:  # Allow empty string for root
        return jsonify({'error': 'Missing path parameter'}), 400

    try:
        full_path = _path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404

        image_data = image_file.read()
        mime_type = image_file.mimetype

        if recursive:
            results = update_folder_pictures(full_path, image_data, mime_type)
            suffix = ''
        else:
            results = update_folder_pictures_only_current(
                full_path, image_data, mime_type
            )
            suffix = ' in current folder'

        return jsonify({
            'success': True,
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': (
                f"Updated cover art for {results['updated']} of "
                f"{results['total']} files{suffix}"
            )
        })

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)


# GET /api/metadata?path=<file_path>&includePicture=<bool>
# Fetch all metadata for a specific file
@bp.route('/api/metadata', methods=['GET'])
@token_required
def get_metadata():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    include_picture = request.args.get('includePicture', 'true').lower() != 'false'

    try:
        full_path = _path(file_path)
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
@bp.route('/api/metadata/file', methods=['POST'])
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
        full_path = _path(file_path)
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
@bp.route('/api/metadata/folder', methods=['POST'])
@token_required
def update_folder_files():
    return _update_folder_field(recursive=True)

# GET /api/audio?path=<file_path>
# Fetch audiofile
@bp.route('/api/audio', methods=['GET'])
@token_required
def serve_audio():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    try:
        full_path = _path(file_path)
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

# POST /api/metadata/picture/file
# Update cover art for a single file
@bp.route('/api/metadata/picture/file', methods=['POST'])
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
        full_path = _path(file_path)
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
@bp.route('/api/metadata/picture/url', methods=['POST'])
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
        full_path = _path(file_path)
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


def _update_folder_cover_from_url(recursive):
    """Set the cover from a remote URL on every file in a folder."""
    data, error = _json_object()
    if error:
        return error
    image_url = data.get('url')
    folder_path = data.get('path')

    if not image_url or folder_path is None:  # Allow empty string for root
        return jsonify({'error': 'Missing url or path parameter'}), 400

    try:
        full_path = _path(folder_path)
        if not os.path.isdir(full_path):
            return jsonify({'error': 'Folder not found'}), 404

        # Fetch once through the SSRF guard, then write the same image to
        # every file instead of downloading it per track.
        image_data, mime_type = fetch_image(
            image_url, f'metadata-docker/{APP_VERSION}'
        )

        if recursive:
            results = update_folder_pictures(full_path, image_data, mime_type)
            suffix = ''
        else:
            results = update_folder_pictures_only_current(
                full_path, image_data, mime_type
            )
            suffix = ' in current folder'

        return jsonify({
            'success': True,
            'updated': results['updated'],
            'failed': results['failed'],
            'total': results['total'],
            'message': (
                f"Updated cover art for {results['updated']} of "
                f"{results['total']} files{suffix}"
            )
        })

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


@bp.route('/api/metadata/picture/preview', methods=['GET'])
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
@bp.route('/api/metadata/picture/folder', methods=['POST'])
@token_required
def update_folder_pictures_endpoint():
    """Update cover art for all files in a folder."""
    return _update_folder_cover(recursive=True)
    
# POST /api/metadata/folder/current
# Update a single metadata field for all files in a folder (current folder only, no subfolders)
@bp.route('/api/metadata/folder/current', methods=['POST'])
@token_required
def update_folder_files_current_only():
    return _update_folder_field(recursive=False)

# POST /api/metadata/picture/folder/current
# Update cover art for all files in a folder (current folder only, no subfolders)
@bp.route('/api/metadata/picture/folder/current', methods=['POST'])
@token_required
def update_folder_pictures_current_only_endpoint():
    """Update cover art for all files in a folder (current folder only, no subfolders)."""
    return _update_folder_cover(recursive=False)


# POST /api/metadata/picture/url/folder
# Update cover art for all files in a folder using a remote URL
@bp.route('/api/metadata/picture/url/folder', methods=['POST'])
@token_required
def update_folder_pictures_from_url_endpoint():
    """Update cover art for all files in a folder using a remote URL."""
    return _update_folder_cover_from_url(recursive=True)


# POST /api/metadata/picture/url/folder/current
# Update cover art for all files in a folder using a remote URL (current folder only)
@bp.route('/api/metadata/picture/url/folder/current', methods=['POST'])
@token_required
def update_folder_pictures_from_url_current_only_endpoint():
    """Update cover art for all files in a folder using a remote URL (no subfolders)."""
    return _update_folder_cover_from_url(recursive=False)


# POST /api/metadata/field/delete
# Delete a specific metadata field from a file or all files in a folder
@bp.route('/api/metadata/field/delete', methods=['POST'])
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
        full_path = _path(path)

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
@bp.route('/api/metadata/picture/delete', methods=['POST'])
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
        full_path = _path(file_path)
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
@bp.route('/api/image', methods=['GET'])
@token_required
def serve_image():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400
    try:
        full_path = _path(file_path)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Determine mimetype. Only the image types listed in the tree are
        # served; anything else would expose arbitrary library files through a
        # content-type-free endpoint.
        mimetype = image_mime_for(full_path)
        if mimetype is None:
            return jsonify({'error': 'Not an image file'}), 400
        
        return send_file(full_path, mimetype=mimetype)
    
    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)

# POST /api/metadata/picture/save-as-file
# Extract cover art from audio file and save as cover.jpg in the same folder
@bp.route('/api/metadata/picture/save-as-file', methods=['POST'])
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
        full_path = _path(file_path)
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

