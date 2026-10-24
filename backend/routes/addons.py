"""Addon endpoints: list the discovered fetchers and proxy their searches.

The plugin manager is created here, at import time, so the blueprint owns its
state. ``app.py`` re-exports it for the tests and for anything else that needs
the registry.
"""

from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from addon_base import EXTRA_INFO_FIELD
from auth import token_required
from errors import _server_error
from logger_config import log_error
from plugin_manager import PluginManager

bp = Blueprint('addons', __name__)

plugin_manager = PluginManager()
plugin_manager.discover_plugins()


# Addons historically returned release dates under "year", track numbers under
# "track", and disk numbers under "disk". The main fields are now "date",
# "trackNumber", and "diskNumber", so keep old addons working without writing
# YEAR/TRACK/DISK tags.
def _normalize_addon_metadata(metadata):
    if not isinstance(metadata, dict):
        return metadata
    normalized = dict(metadata)
    for legacy, current in (
        ('year', 'date'),
        ('track', 'trackNumber'),
        ('disk', 'diskNumber'),
        ('extra_info', EXTRA_INFO_FIELD),
    ):
        if legacy in normalized and not normalized.get(current):
            normalized[current] = normalized.pop(legacy)
    return normalized


def _addon_version(fetcher_cls):
    value = getattr(fetcher_cls, 'version', '')
    return '' if value is None else str(value).strip()


def _addon_github_url(fetcher_cls):
    """Return a validated GitHub URL declared by an addon, if any."""
    raw = ''
    for attr in ('github', 'github_url', 'github_link', 'repository', 'homepage'):
        value = getattr(fetcher_cls, attr, '')
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            break

    if raw.startswith(('github.com/', 'www.github.com/')):
        raw = 'https://' + raw
    if not raw:
        return ''

    parsed = urlparse(raw)
    if parsed.scheme != 'https':
        return ''
    if parsed.username or parsed.password:
        return ''
    if (parsed.hostname or '').lower() not in ('github.com', 'www.github.com'):
        return ''
    return raw


@bp.route('/api/addons', methods=['GET'])
@token_required
def list_addons():
    result = []
    for fetcher_id, fetcher_cls in plugin_manager.fetchers.items():
        try:
            # Check which methods are actually implemented (not NotImplementedError)
            methods = []
            instance = fetcher_cls()

            if not getattr(instance.search_albums, '_default_implementation', False):
                methods.append('search_albums')
            if not getattr(instance.fetch_album_metadata, '_default_implementation', False):
                methods.append('fetch_album_metadata')
            if not getattr(instance.search_songs, '_default_implementation', False):
                methods.append('search_songs')
            if not getattr(instance.fetch_song_metadata, '_default_implementation', False):
                methods.append('fetch_song_metadata')

            result.append({
                "id": fetcher_cls.id,
                "name": fetcher_cls.name,
                "description": fetcher_cls.description,
                "version": _addon_version(fetcher_cls),
                "github": _addon_github_url(fetcher_cls),
                "required_env_vars": getattr(fetcher_cls, 'required_env_vars', []),
                "methods": methods
            })
        except Exception as e:
            log_error(f"Fetcher '{fetcher_id}' failed to initialize: {e}")
            # Skip fetcher if any exception raised
            continue
    return jsonify({"fetchers": result})


@bp.route('/api/addons/<fetcher_id>/search_songs', methods=['GET'])
@token_required
def search_songs(fetcher_id):
    query = request.args.get('query')
    limit = max(1, min(request.args.get('limit', 5, type=int), 50))

    if not query:
        return jsonify({"success": False, "error": "Missing 'query' parameter"}), 400

    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        results = instance.search_songs(query, limit)
        results = [_normalize_addon_metadata(result) for result in results]
        return jsonify({"success": True, "results": results})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Song search not supported by this fetcher"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)


@bp.route('/api/addons/<fetcher_id>/fetch_song/<song_id>', methods=['GET'])
@token_required
def fetch_song_metadata(fetcher_id, song_id):
    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        metadata = instance.fetch_song_metadata(song_id)
        return jsonify({"success": True, "metadata": _normalize_addon_metadata(metadata)})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Fetch song metadata not supported"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)


@bp.route('/api/addons/<fetcher_id>/search_albums', methods=['GET'])
@token_required
def search_albums(fetcher_id):
    query = request.args.get('query')
    limit = max(1, min(request.args.get('limit', 5, type=int), 50))

    if not query:
        return jsonify({"success": False, "error": "Missing 'query' parameter"}), 400

    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        results = instance.search_albums(query, limit)
        results = [_normalize_addon_metadata(result) for result in results]
        return jsonify({"success": True, "results": results})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Album search not supported by this fetcher"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)


@bp.route('/api/addons/<fetcher_id>/fetch_album/<album_id>', methods=['GET'])
@token_required
def fetch_album_metadata(fetcher_id, album_id):
    fetcher_cls = plugin_manager.get_fetcher(fetcher_id)
    if not fetcher_cls:
        return jsonify({"success": False, "error": f"Fetcher '{fetcher_id}' not found"}), 404

    try:
        instance = fetcher_cls()
        metadata = instance.fetch_album_metadata(album_id)
        if isinstance(metadata, list):
            metadata = [_normalize_addon_metadata(track) for track in metadata]
        else:
            metadata = _normalize_addon_metadata(metadata)
        return jsonify({"success": True, "metadata": metadata})
    except NotImplementedError:
        return jsonify({"success": False, "error": "Fetch album metadata not supported"}), 400
    except Exception as e:
        return _server_error(e, 'The addon failed to complete the request.', success=False)
