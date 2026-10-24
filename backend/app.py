import os
from auth import (
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    TOKEN_SCOPE_DOWNLOAD,
    TOKEN_SCOPE_SESSION,
    login as auth_login,
    reset_rate_limiter,
    token_required,
)
from routes import register_blueprints
from routes.addons import _addon_github_url, plugin_manager
from routes.system import (
    _compare_versions,
    _version_cache,
    get_version_info,
)
from errors import register_error_handlers
from library import build_tree as _build_tree, natural_key
from paths import (
    generated_rename_path,
    is_library_root,
    is_within as _is_within,
    safe_path as resolve_safe_path,
)
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from logger_config import log_info, log_error, log_warning, LOG_DIR

from config import (
    APP_GIT_SHA,
    APP_VERSION,
    AUTH_PASSWORD,
    AUTH_PASSWORD_HASH,
    AUTH_USERNAME,
    CACHE_TTL_SECONDS,
    COVER_UPLOAD_BYTES,
    COVER_UPLOAD_PATHS,
    DEBUG,
    DISABLE_VERSION_CHECK,
    GITHUB_REPO_NAME,
    GITHUB_REPO_OWNER,
    JWT_SECRET_KEY,
    MAX_UPLOAD_BYTES,
    MUSIC_ROOT,
    PGID,
    PUID,
    STORAGE_HEADROOM_BYTES,
    TEXT_MAX_BYTES,
    TOKEN_EXPIRE_HOURS,
    format_size as _format_size,
)

log_info("STARTING")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')


def build_tree(current_path, relative_path):
    return _build_tree(current_path, relative_path, MUSIC_ROOT)


# Path helpers live in paths.py. These wrappers bind the library root so the
# existing tests can keep calling app_module.<helper>.
def _is_library_root(path):
    """Return True when *path* resolves to the music library root itself."""
    return is_library_root(path, MUSIC_ROOT)


def _generated_rename_path(parent, name):
    """Validate a generated rename target and return its full path."""
    return generated_rename_path(parent, name, MUSIC_ROOT)


def safe_path(file_path):
    """Resolve a user-supplied path and keep it inside the music folder."""
    return resolve_safe_path(file_path, MUSIC_ROOT)


log_info(f'Debug set to {DEBUG}')
log_info(f'PUID set to {PUID}')
log_info(f'PGID set to {PGID}')

log_info(f'Music folder: {Path(MUSIC_ROOT).absolute()}')
log_info(f'Log folder:{Path(LOG_DIR).absolute()}')
log_info(
    f'Upload limit: {_format_size(MAX_UPLOAD_BYTES)} per request; '
    f'cover images: {_format_size(COVER_UPLOAD_BYTES)}'
)


def create_app(settings=None):
    """Build the Flask application.

    ``settings`` is an optional mapping merged into ``app.config``. Paths,
    credentials and limits come from ``config.py``; the module-level ``app``
    below is built with those defaults so ``gunicorn app:app`` is unchanged.
    """
# Flask's built-in static route has the same `/<path>` shape as `serve` below
# and shadows it. It is disabled so `serve` is the single place that applies
# cache headers and the SPA fallback.
    app = Flask(__name__, static_folder=None)
    app.config['SECRET_KEY'] = JWT_SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES
    if settings:
        app.config.update(settings)
    register_error_handlers(app)
    register_blueprints(app)

    @app.before_request
    def limit_cover_upload_size():
        """Apply the smaller body limit to cover-art uploads."""
        if request.path in COVER_UPLOAD_PATHS:
            request.max_content_length = COVER_UPLOAD_BYTES

    # The handler, token scopes and the rate limiter live in auth.py so that
    # module never has to import this one.
    @app.route('/api/login', methods=['POST'])
    def login():
        return auth_login()

    @app.route('/api/validate', methods=['GET'])
    @token_required
    def validate_token():
        """Simple endpoint to check if token is valid."""
        return jsonify({'valid': True})

    # Serve Svelte frontend
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        # Unknown API routes are never the SPA: a JSON parse error in the
        # browser would be more confusing than a clear 404.
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

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=DEBUG)
