"""Text file endpoints: read and atomically save ``.txt`` / ``.lrc`` files."""

import os
import secrets

from flask import Blueprint, jsonify, request

from auth import token_required
from config import MUSIC_ROOT, TEXT_MAX_BYTES, format_size
from errors import _json_object, _permission_error, _server_error
from formats import TEXT_EXTENSIONS
from logger_config import log_info
from paths import safe_path

bp = Blueprint('text', __name__)


@bp.route('/api/text', methods=['GET'])
@token_required
def get_text_file():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Missing path parameter'}), 400

    try:
        full_path = safe_path(file_path, MUSIC_ROOT)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        # Restrict to text files
        if not full_path.lower().endswith(TEXT_EXTENSIONS):
            return jsonify({'error': 'Not a text file'}), 400

        try:
            size = os.path.getsize(full_path)
        except OSError:
            size = None
        if size is not None and size > TEXT_MAX_BYTES:
            return jsonify({
                'error': f'The text file is too large. The maximum size is {format_size(TEXT_MAX_BYTES)}.'
            }), 413

        # Undecodable bytes must not make the editor fail with a 500; the
        # replacement character is visible and the file can still be fixed.
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(TEXT_MAX_BYTES + 1)

        if len(content) > TEXT_MAX_BYTES:
            return jsonify({
                'error': f'The text file is too large. The maximum size is {format_size(TEXT_MAX_BYTES)}.'
            }), 413

        return jsonify({'content': content})

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)


@bp.route('/api/text/save', methods=['POST'])
@token_required
def save_text_file():
    data, error = _json_object()
    if error:
        return error
    file_path = data.get('path')
    content = data.get('content')

    if not file_path or content is None:
        return jsonify({'error': 'Missing path or content'}), 400
    if not isinstance(content, str):
        return jsonify({'error': 'content must be a string'}), 400
    if len(content.encode('utf-8')) > TEXT_MAX_BYTES:
        return jsonify({
            'error': f'The text content is too large. The maximum size is {format_size(TEXT_MAX_BYTES)}.'
        }), 413

    try:
        full_path = safe_path(file_path, MUSIC_ROOT)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        if not full_path.lower().endswith(TEXT_EXTENSIONS):
            return jsonify({'error': 'Not a text file'}), 400

        # Write to a hidden temp file in the same directory first: a failed
        # write must not truncate the existing lyrics or notes.
        directory = os.path.dirname(full_path) or '.'
        temp_path = os.path.join(directory, f'.upload-{secrets.token_hex(8)}.part')
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, full_path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        log_info(f"Updated text file: {full_path}")
        return jsonify({'success': True})

    except PermissionError as e:
        return _permission_error(e)
    except Exception as e:
        return _server_error(e)
