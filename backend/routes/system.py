"""System endpoints: the health check and the lazy GitHub release check.

The first version check happens on the first ``/api/version`` request, not at
import time, so an offline install starts immediately (B-26).
"""

import datetime
import time

import requests
from flask import Blueprint, jsonify

from config import (
    APP_GIT_SHA,
    APP_VERSION,
    CACHE_TTL_SECONDS,
    DISABLE_VERSION_CHECK,
    GITHUB_REPO_NAME,
    GITHUB_REPO_OWNER,
    MAX_UPLOAD_BYTES,
)
from logger_config import log_error, log_info, log_warning

bp = Blueprint('system', __name__)

# Cache for version info. Updated in place so every module that imported the
# dict (the test suite resets it) sees the same values.
_version_cache = {
    'latest': None,
    'update_available': False,
    'timestamp': 0
}


def _compare_versions(current: str, pulled: str) -> bool:
    """Return True if pulled version is newer than current."""
    # Strip 'v' or 'V' and split by '.'
    curr_parts = [int(x) for x in current.lower().lstrip('v').split('.')]
    pull_parts = [int(x) for x in pulled.lower().lstrip('v').split('.')]
    return pull_parts > curr_parts


def get_version_info():
    """Return current and latest version info, refreshing cache if stale."""
    # If version check is disabled, return base info without fetching
    if DISABLE_VERSION_CHECK:
        return {
            'current': APP_VERSION,
            'latest': None,
            'update_available': False
        }

    now = time.time()
    # Return cached data if still fresh
    if _version_cache['timestamp'] and (now - _version_cache['timestamp'] < CACHE_TTL_SECONDS):
        return {
            'current': APP_VERSION,
            'latest': _version_cache['latest'],
            'update_available': _version_cache['update_available']
        }

    # Cache expired or empty – fetch from GitHub
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest = data.get('tag_name', '')
            if latest:
                update_available = _compare_versions(APP_VERSION, latest)
                _version_cache.update({
                    'latest': latest,
                    'update_available': update_available,
                    'timestamp': now
                })
                if update_available:
                    log_info('Version: Update available, check GitHub for more info')
                else:
                    log_info('Version: Up to date')
            else:
                log_warning("GitHub release tag_name is empty")
                _version_cache['timestamp'] = now
                return {
                    'current': APP_VERSION,
                    'latest': _version_cache.get('latest'),
                    'update_available': False
                }
        else:
            log_warning(f"GitHub API returned {response.status_code}")
            _version_cache['timestamp'] = now
            return {
                'current': APP_VERSION,
                'latest': _version_cache.get('latest'),
                'update_available': False
            }
    except Exception as e:
        log_error(f"Failed to check for updates: {e}")
        _version_cache['timestamp'] = now
        return {
            'current': APP_VERSION,
            'latest': _version_cache.get('latest'),
            'update_available': False
        }

    return {
        'current': APP_VERSION,
        'latest': _version_cache['latest'],
        'update_available': _version_cache['update_available']
    }


@bp.route('/api/version', methods=['GET'])
def get_version():
    info = get_version_info()
    return jsonify({
        'current_version': info['current'],
        'latest_version': info['latest'],
        'update_available': info['update_available'],
        'git_sha': APP_GIT_SHA,
        # Lets the upload UI reject an oversized file before sending it.
        'max_upload_bytes': MAX_UPLOAD_BYTES
    })


@bp.route('/api/ping', methods=['GET'])
def health():
    try:
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception:
        return jsonify({"status": "error"}), 500
