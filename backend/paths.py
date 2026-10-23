"""Path resolution, containment and naming inside the music library.

Every user-supplied path goes through :func:`safe_path`. Every path derived
from an already-validated one is checked with :func:`is_within`, which compares
resolved paths with ``commonpath`` instead of ``str.startswith`` so a sibling
such as ``/music-other`` is never treated as being inside ``/music``.

The library root is a parameter rather than module state: the app factory
builds it once from the environment and passes it in.
"""

import os

from errors import AccessDenied


def is_within(base_path, candidate_path):
    """Return True when *candidate_path* is *base_path* or lives below it.

    Both paths are resolved with ``realpath`` first, so a symlink cannot be
    used to point outside *base_path*.
    """
    try:
        base = os.path.realpath(base_path)
        candidate = os.path.realpath(candidate_path)
        return os.path.commonpath([base, candidate]) == base
    except ValueError:
        # Different drives on Windows cannot share a common path.
        return False


def is_library_root(path, music_root):
    """Return True when *path* resolves to the music library root itself.

    ``safe_path()`` maps ``""``, ``"."`` and ``"/"`` to the root. Removing that
    tree, or deriving a sibling name from it, would act outside the library.
    """
    try:
        return os.path.realpath(path) == os.path.realpath(music_root)
    except (OSError, ValueError):
        return False


def unique_path(path):
    """Return *path* or the first free "name (n).ext" variant."""
    base, ext = os.path.splitext(path)
    counter = 1
    candidate = path
    while os.path.exists(candidate):
        candidate = f'{base} ({counter}){ext}'
        counter += 1
    return candidate


def generated_rename_path(parent, name, music_root):
    """Validate a generated rename target and return its full path.

    Smart rename builds names from tag values, so the result is not a
    user-typed filename. Reject empty names, ``.``/``..``, separators and
    names that would resolve outside the music library.
    """
    if not isinstance(name, str) or not name or '\0' in name:
        raise ValueError('Invalid generated name')
    if name in ('.', '..') or name.strip() != name:
        raise ValueError('Invalid generated name')
    if os.path.isabs(name) or '/' in name or '\\' in name:
        raise ValueError('Invalid generated name')

    new_path = os.path.join(parent, name)
    if not is_within(music_root, new_path):
        raise ValueError('Invalid generated name')
    return new_path


def safe_path(file_path, music_root):
    """Resolve a user-supplied path and keep it inside the music folder.

    Leading slashes are ignored so both ``/album/song.mp3`` and
    ``album/song.mp3`` refer to the library root. Symlinks are resolved for
    the containment check, so a link inside the library cannot point outside
    it. Raises ``PermissionError`` when the resolved path would escape
    ``music_root``.
    """
    if file_path is None or '\0' in str(file_path):
        raise AccessDenied('Invalid path.')

    full_path = os.path.abspath(
        os.path.join(music_root, str(file_path).lstrip('/'))
    )
    if not is_within(music_root, full_path):
        raise AccessDenied('Path is outside the music library.')
    return full_path
