"""Download endpoints: direct downloads and short-lived download tokens.

Download tokens are short-lived so they can be used in a native browser
download URL without exposing the long-lived auth token.
"""

import datetime
import os
from urllib.parse import quote

import jwt
from flask import Blueprint, Response, jsonify, request, send_file

from auth import TOKEN_SCOPE_DOWNLOAD, token_required
from config import AUTH_USERNAME, JWT_SECRET_KEY, MUSIC_ROOT
from errors import _json_object, _permission_error, _server_error
from formats import mime_for
from logger_config import log_info
from paths import safe_path
from zip_stream import iter_zip

bp = Blueprint('downloads', __name__)

DOWNLOAD_TOKEN_EXPIRE_SECONDS = 120

_IMAGE_MIMETYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp',
    '.webp': 'image/webp',
}


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
        full_path = safe_path(path, MUSIC_ROOT)
        if not os.path.exists(full_path):
            return jsonify({'error': 'Path not found'}), 404

        # Handle single file download
        if not is_folder and os.path.isfile(full_path):
            # Determine mimetype using the format registry, with image
            # fallbacks for non-audio downloads.
            ext = os.path.splitext(full_path)[1].lower()
            mimetype = mime_for(
                full_path,
                default=_IMAGE_MIMETYPES.get(ext, 'application/octet-stream'),
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


@bp.route('/api/download-token', methods=['POST'])
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
        full_path = safe_path(path, MUSIC_ROOT)
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
    }, JWT_SECRET_KEY, algorithm='HS256')

    return jsonify({
        'token': token,
        'filename': filename,
        'expires_in': DOWNLOAD_TOKEN_EXPIRE_SECONDS
    })


@bp.route('/api/download', methods=['GET'])
def download_item_with_token():
    """Download a file or folder using a short-lived download token."""
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Token is missing'}), 401

    try:
        data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Download link has expired'}), 401
    except Exception:
        return jsonify({'error': 'Token is invalid'}), 401

    if data.get('scope') != TOKEN_SCOPE_DOWNLOAD or not data.get('path'):
        return jsonify({'error': 'Token is invalid'}), 401

    if data.get('username') != AUTH_USERNAME:
        return jsonify({'error': 'Token is invalid'}), 401

    return _send_download(data['path'], bool(data.get('isFolder', False)))


@bp.route('/api/download', methods=['POST'])
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
