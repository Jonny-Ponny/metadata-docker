"""Authentication: login, session tokens and the login rate limiter.

``token_required`` guards every API route except login, ping, version and the
SPA fallback. The limiter is in-memory and per-IP: the container runs a single
gunicorn worker, so it is shared by all threads. It resets on restart, which is
acceptable for a single-admin app; a multi-worker deployment would need shared
storage.
"""

import datetime
import hmac
import threading
import time
from functools import wraps

import jwt
from flask import jsonify, request
from werkzeug.security import check_password_hash

from config import (
    AUTH_PASSWORD,
    AUTH_PASSWORD_HASH,
    AUTH_USERNAME,
    JWT_SECRET_KEY,
    TOKEN_EXPIRE_HOURS,
)

# Token scopes. Session tokens authenticate API requests; download tokens only
# authorize a single download via the /api/download?token=... URL. Keeping the
# scopes distinct prevents a download token (which can leak through URLs, proxy
# logs or browser history) from being used as a full session token.
TOKEN_SCOPE_SESSION = 'session'
TOKEN_SCOPE_DOWNLOAD = 'download'

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
_login_failures = {}
_login_failures_lock = threading.Lock()


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Check for token in Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            # Decode token
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            # Only session tokens may authenticate API requests. Download
            # tokens (scope 'download') must be rejected here.
            if data.get('scope') != TOKEN_SCOPE_SESSION:
                raise Exception('Not a session token')
            current_user = data.get('username')
            if not current_user or current_user != AUTH_USERNAME:
                raise Exception('Invalid user')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except Exception:
            return jsonify({'error': 'Token is invalid'}), 401

        return f(*args, **kwargs)

    return decorated


def _constant_time_eq(value, expected):
    """Compare two strings without leaking content or length through timing."""
    return hmac.compare_digest(value.encode('utf-8'), expected.encode('utf-8'))


def _password_matches(password):
    if AUTH_PASSWORD_HASH:
        try:
            return check_password_hash(AUTH_PASSWORD_HASH, password)
        except (ValueError, TypeError):
            # Startup validation should prevent this, but never turn a bad
            # configuration into a 500 on the login endpoint.
            return False
    return _constant_time_eq(password, AUTH_PASSWORD)


def _client_ip():
    # Behind a reverse proxy this is the proxy's address unless a trusted
    # proxy header is configured, so the limiter remains a global limit there.
    return request.remote_addr or 'unknown'


def _login_retry_after(ip):
    """Return seconds until this IP may try again, or 0 if it may try now."""
    now = time.time()
    with _login_failures_lock:
        entry = _login_failures.get(ip)
        if not entry:
            return 0
        if entry['locked_until'] > now:
            return max(1, int(entry['locked_until'] - now + 0.999))
        if now - entry['first'] >= LOGIN_LOCKOUT_SECONDS:
            _login_failures.pop(ip, None)
        return 0


def _record_login_failure(ip):
    """Record a failed attempt and return retry-after seconds when locked."""
    now = time.time()
    with _login_failures_lock:
        entry = _login_failures.get(ip)
        if not entry or now - entry['first'] >= LOGIN_LOCKOUT_SECONDS:
            entry = {'count': 0, 'first': now, 'locked_until': 0}

        entry['count'] += 1
        retry_after = 0
        if entry['count'] >= LOGIN_MAX_ATTEMPTS:
            entry['locked_until'] = now + LOGIN_LOCKOUT_SECONDS
            retry_after = LOGIN_LOCKOUT_SECONDS
        _login_failures[ip] = entry

        # Keep the table bounded if many client addresses are seen.
        if len(_login_failures) > 4096:
            stale = [
                key for key, value in _login_failures.items()
                if value['locked_until'] <= now
                and now - value['first'] >= LOGIN_LOCKOUT_SECONDS
            ]
            for key in stale:
                _login_failures.pop(key, None)

    return retry_after


def _clear_login_failures(ip):
    with _login_failures_lock:
        _login_failures.pop(ip, None)


def reset_rate_limiter():
    """Forget every failed login attempt. Used by the test suite."""
    with _login_failures_lock:
        _login_failures.clear()


def _rate_limited_response(retry_after):
    response = jsonify({'error': 'Too many failed login attempts. Try again later.'})
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


def login():
    """Verify the credentials and return a session token."""
    client_ip = _client_ip()
    retry_after = _login_retry_after(client_ip)
    if retry_after:
        return _rate_limited_response(retry_after)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Username and password required'}), 400

    username = data.get('username')
    password = data.get('password')

    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if len(username) > 256 or len(password) > 4096:
        return jsonify({'error': 'Invalid credentials'}), 401

    username_ok = _constant_time_eq(username, AUTH_USERNAME)
    password_ok = _password_matches(password)

    if not (username_ok and password_ok):
        retry_after = _record_login_failure(client_ip)
        if retry_after:
            return _rate_limited_response(retry_after)
        return jsonify({'error': 'Invalid credentials'}), 401

    _clear_login_failures(client_ip)

    # Generate token with configurable expiry
    token = jwt.encode({
        'username': AUTH_USERNAME,
        'scope': TOKEN_SCOPE_SESSION,
        'exp': datetime.datetime.now() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS)
    }, JWT_SECRET_KEY, algorithm='HS256')

    return jsonify({
        'success': True,
        'token': token,
        'username': AUTH_USERNAME,
        'expires_in': TOKEN_EXPIRE_HOURS * 3600  # in seconds
    })
