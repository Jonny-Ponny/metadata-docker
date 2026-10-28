"""Environment-driven settings for the backend.

Everything here is read once, at import time. The values are module constants
rather than an object because the route bodies import them directly.
``create_app()`` accepts an optional config mapping for tests, but it does not
re-read the environment: changing these values requires a process restart.

Only names that depend on the environment (or on the version we ship) belong in
this module. Feature constants such as the upload conflict policies stay with
the code that uses them.
"""

import os
import secrets

from werkzeug.security import check_password_hash

from logger_config import log_warning


def _env_int(name, default, minimum=1, unit=''):
    """Read an integer >= *minimum* from the environment, or use *default*."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw)
    except ValueError:
        value = 0

    if value < minimum:
        suffix = f' {unit}' if unit else ''
        log_warning(f'Invalid {name}={raw!r}; using {default}{suffix}')
        return default
    return value


def _env_size_mib(name, default_mib):
    """Read a positive size in MiB from the environment."""
    return _env_int(name, default_mib, unit='MiB') * 1024 * 1024


def format_size(size):
    """Render a byte limit as GiB or MiB for user-facing messages."""
    if size >= 1024 ** 3 and size % (1024 ** 3) == 0:
        return f'{size // (1024 ** 3)} GiB'
    return f'{size // (1024 ** 2)} MiB'


DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')

# One env var, one value: MUSIC_ROOT is always absolute, and nothing else
# re-reads MUSIC_FOLDER. An empty value falls back to the container path.
MUSIC_ROOT = os.path.abspath(os.getenv('MUSIC_FOLDER') or '/music')

# If not in environment docker will run as root
PUID = os.getenv('PUID', '0')
PGID = os.getenv('PGID', '0')

# Auth config from environment. Missing or empty credentials never fall back
# to a known default. Instead, generate temporary random credentials for this
# process and log them once, so an unconfigured deployment cannot be accessed
# with a guessable password. Set AUTH_USERNAME and AUTH_PASSWORD (or
# AUTH_PASSWORD_HASH) for a stable login.
AUTH_USERNAME = os.getenv('AUTH_USERNAME') or ''
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD') or ''
AUTH_PASSWORD_HASH = os.getenv('AUTH_PASSWORD_HASH') or ''

_generated_username = not AUTH_USERNAME
_generated_password = False

if _generated_username:
    AUTH_USERNAME = f'admin_{secrets.token_hex(4)}'

if AUTH_PASSWORD_HASH and AUTH_PASSWORD:
    log_warning('Both AUTH_PASSWORD and AUTH_PASSWORD_HASH are set; using AUTH_PASSWORD_HASH')
    AUTH_PASSWORD = ''

if AUTH_PASSWORD_HASH:
    # Validate the hash at startup so a typo does not silently reject every
    # login. Werkzeug hashes look like "scrypt:...$salt$hash" (or the older
    # pbkdf2 format). Never crash-loop the container over a bad value: log the
    # problem and fall through to a temporary password for this run.
    hash_error = None
    if AUTH_PASSWORD_HASH.count('$') < 2:
        hash_error = 'expected "method$salt$hash"'
    else:
        try:
            check_password_hash(AUTH_PASSWORD_HASH, 'startup-validation')
        except (ValueError, TypeError) as e:
            hash_error = str(e)
    if hash_error:
        log_warning(
            'AUTH_PASSWORD_HASH is not a valid Werkzeug password hash '
            f'({hash_error}); generating a temporary password for this run.'
        )
        log_warning(
            'Generate a valid hash with: python -c "from werkzeug.security '
            'import generate_password_hash; print(generate_password_hash('
            "'your-password'))\""
        )
        AUTH_PASSWORD_HASH = ''
        # Do not reuse a plaintext password that was shadowed by the bad hash;
        # the temporary password is the only credential logged for this run.
        AUTH_PASSWORD = ''

if not AUTH_PASSWORD and not AUTH_PASSWORD_HASH:
    AUTH_PASSWORD = secrets.token_urlsafe(24)
    _generated_password = True

if _generated_username or _generated_password:
    log_warning('=' * 70)
    log_warning('AUTH_USERNAME/AUTH_PASSWORD are not fully configured.')
    log_warning('Temporary credentials for this run (they change on every restart):')
    log_warning(f'  username: {AUTH_USERNAME}{" (generated)" if _generated_username else ""}')
    if _generated_password:
        log_warning(f'  password: {AUTH_PASSWORD} (generated)')
    elif AUTH_PASSWORD_HASH:
        log_warning('  password: (from AUTH_PASSWORD_HASH)')
    else:
        log_warning('  password: (from AUTH_PASSWORD)')
    log_warning('Set AUTH_USERNAME and AUTH_PASSWORD (or AUTH_PASSWORD_HASH) for a stable login.')
    log_warning('=' * 70)

if not AUTH_PASSWORD_HASH and (
    AUTH_PASSWORD.lower() in ('admin', 'password', 'changeme')
    or AUTH_PASSWORD == AUTH_USERNAME
):
    log_warning('AUTH_PASSWORD is weak or matches the username. Set a strong password before exposing the app.')


# Optional stable JWT secret. Without it, every process start generates a new
# one and a restart invalidates all sessions. A configured value shorter than
# 32 characters is ignored with a warning instead of weakening token signatures.
_JWT_SECRET_ENV = os.getenv('JWT_SECRET') or ''
if _JWT_SECRET_ENV and len(_JWT_SECRET_ENV) < 32:
    log_warning(
        'JWT_SECRET is shorter than 32 characters; using a random per-process '
        'secret instead. Sessions will be invalidated on restart.'
    )
    _JWT_SECRET_ENV = ''
JWT_SECRET_KEY = _JWT_SECRET_ENV or secrets.token_hex(24)

TOKEN_EXPIRE_HOURS = _env_int('TOKEN_EXPIRE_HOURS', 12)

# Body limits are per request. Drag-and-drop folder uploads send one request
# per file, so this caps a single file rather than the whole library.
MAX_UPLOAD_BYTES = _env_size_mib('MAX_UPLOAD_MB', 4096)
COVER_UPLOAD_BYTES = 20 * 1024 * 1024
# Text files (lyrics, notes) are edited in the browser, so keep them small
# enough to read and write in one request.
TEXT_MAX_BYTES = 1024 * 1024
# Free-space preflight leaves this much headroom in the library.
STORAGE_HEADROOM_BYTES = 256 * 1024 * 1024

# Routes that accept cover art use the smaller body limit.
COVER_UPLOAD_PATHS = frozenset({
    '/api/metadata/picture/file',
    '/api/metadata/picture/folder',
    '/api/metadata/picture/folder/current',
})

APP_VERSION = 'v1.1.0'
# Commit the image was built from, set at build time (see Dockerfile). Lets
# users compare a running container against the build-provenance attestation.
APP_GIT_SHA = os.getenv('APP_GIT_SHA', 'unknown')
GITHUB_REPO_OWNER = 'Jonny-Ponny'
GITHUB_REPO_NAME = 'metadata-docker'

CACHE_TTL_SECONDS = _env_int('CACHE_TTL_SECONDS', 3600)

DISABLE_VERSION_CHECK = os.getenv('DISABLE_VERSION_CHECK', 'False').lower() in ('true', '1', 'yes', 'on')
