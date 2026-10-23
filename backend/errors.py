"""Public error responses, JSON body validation and the security headers.

Routes raise real exceptions; this module is the single place that decides what
the client is allowed to see. Exception details go to the log, the response
carries a short message and the matching status code.

``register_error_handlers(app)`` attaches the JSON handlers and the
defense-in-depth headers, so the app factory in step 10 can reuse it.
"""

import errno

import requests
from flask import jsonify, request

from config import (
    COVER_UPLOAD_BYTES,
    COVER_UPLOAD_PATHS,
    MAX_UPLOAD_BYTES,
    format_size,
)
from logger_config import log_error, log_warning


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


def _json_object():
    """Return ``(data, error_response)`` for a JSON object request body.

    ``request.get_json()`` raises before the route can validate anything when
    the ``Content-Type`` or the body is wrong, and a JSON list or string then
    breaks ``data.get()`` with a 500. Every JSON route uses this helper so
    those cases stay JSON with a 4xx status.
    """
    if not request.is_json:
        return None, (jsonify({
            'error': 'Request body must be JSON (Content-Type: application/json).'
        }), 415)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'Request body must be a JSON object.'}), 400)

    return data, None


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


def add_security_headers(response):
    response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


def handle_bad_request(error):
    """Return JSON for malformed requests instead of Flask's HTML page."""
    return jsonify({'error': 'Invalid request.'}), 400


def handle_unsupported_media_type(error):
    """Return JSON when a request body has an unsupported content type."""
    return jsonify({'error': 'Unsupported request body; send JSON.'}), 415


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


def handle_request_too_large(error):
    """Return JSON for oversized request bodies instead of an HTML page."""
    if request.path in COVER_UPLOAD_PATHS:
        limit = COVER_UPLOAD_BYTES
        message = f'The image is too large. The maximum size is {format_size(limit)}.'
    elif request.path == '/api/upload':
        limit = MAX_UPLOAD_BYTES
        message = f'The uploaded file is too large. The maximum size is {format_size(limit)}.'
    else:
        limit = MAX_UPLOAD_BYTES
        message = f'The request is too large. The maximum size is {format_size(limit)}.'

    log_warning(
        f'{request.method} {request.path}: body exceeded {format_size(limit)}'
    )
    return jsonify({'error': message}), 413


def register_error_handlers(app):
    """Attach the JSON error handlers and security headers to *app*."""
    app.register_error_handler(400, handle_bad_request)
    app.register_error_handler(413, handle_request_too_large)
    app.register_error_handler(415, handle_unsupported_media_type)
    app.register_error_handler(500, handle_internal_server_error)
    app.after_request(add_security_headers)
