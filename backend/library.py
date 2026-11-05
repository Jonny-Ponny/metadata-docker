"""File-tree classification and natural sorting for the library listing.

``build_tree`` returns the whole library as a nested structure and is used by
``/api/files``. ``build_directory`` returns one directory's entries and backs
the lazy ``/api/files/dir`` endpoint, so the tree can be loaded folder by
folder. Both share ``_scan_entries`` so classification, sorting, symlink
handling and the skipped-upload rule cannot drift apart.

Every directory node carries ``folder_count``, ``file_count`` and
``file_size`` describing its direct children. They let the tree show a folder
summary without walking the folder again on the client, and they are computed
while the directory is already being listed.

The functions take the library root as a parameter (like the helpers in
``paths.py``) so they can be unit-tested against a temporary directory without
importing the Flask app.
"""

import os
import re
import stat

from formats import IMAGE_EXTENSIONS, TEXT_EXTENSIONS, is_supported_audio
from paths import is_within


def natural_key(text):
    """Convert text into a list of strings and numbers for natural sorting.

    ``str.isdigit()`` is true for characters such as ``²`` that ``int()``
    rejects, so only ASCII digits are converted (B-10).
    """
    return [
        int(part) if part.isascii() and part.isdigit() else part.lower()
        for part in re.split(r'(\d+)', text)
    ]


def _is_skipped_upload(entry):
    """True for the hidden ``.upload-*.part`` file of an in-flight upload.

    Uploads are written to a temporary file and renamed into place, so a tree
    listing during a long upload must not show it. Other dotfiles stay visible.
    """
    return entry.startswith('.upload-') and entry.endswith('.part')


def _classify_file(entry, rel, info):
    """Build the tree node for a regular file."""
    if is_supported_audio(entry):
        file_type = 'audio'
    elif entry.lower().endswith(IMAGE_EXTENSIONS):
        file_type = 'image'
    elif entry.lower().endswith(TEXT_EXTENSIONS):
        file_type = 'text'
    else:
        # Everything else is still listed so it can be inspected, renamed,
        # downloaded or deleted. The metadata endpoint marks these files
        # read-only.
        file_type = 'other'
    return {
        'name': entry,
        'type': 'file',
        'file_type': file_type,
        'path': rel,
        'size': info.st_size,
        'created': info.st_ctime,
        'modified': info.st_mtime,
    }


def _listdir_names(path):
    """``os.listdir`` that tolerates a folder vanishing mid-walk (B-11)."""
    try:
        return sorted(os.listdir(path), key=natural_key)
    except (PermissionError, FileNotFoundError):
        return []


def _scan_entries(current_path, relative_path, music_root):
    """List one directory and return an entry tuple per listable child.

    Each tuple is ``(entry, full, rel, info, is_directory)``.

    The listing is tolerant: a permission error, a folder that disappears
    mid-walk (B-11) or an entry that vanishes between ``listdir()`` and
    ``stat()`` yields what could be read instead of failing the request.

    Symlinked directories are skipped: following them can escape the library
    root or recurse forever through a cycle. ``safe_path()`` resolves symlinks
    as well, so anything not listed here could not be opened through the API
    either. A symlinked file is only listed when it resolves inside the
    library, which also avoids exposing a link that points at an arbitrary
    outside file.
    """
    entries = []
    for entry in _listdir_names(current_path):
        if _is_skipped_upload(entry):
            continue
        full = os.path.join(current_path, entry)
        rel = os.path.join(relative_path, entry).replace('\\', '/')
        try:
            info = os.stat(full)
        except OSError:
            continue

        if stat.S_ISDIR(info.st_mode):
            if os.path.islink(full):
                continue
            entries.append((entry, full, rel, info, True))
        elif stat.S_ISREG(info.st_mode):
            if os.path.islink(full) and not is_within(music_root, full):
                continue
            entries.append((entry, full, rel, info, False))

    return entries


def _dir_has_children(path):
    """True when *path* lists at least one child, without failing on errors.

    Used for the lazy endpoint so the folder icon can show whether expanding is
    worthwhile before anything is fetched. It only reads the directory it is
    already being asked about, so it stays cheap on network storage.
    """
    try:
        return bool(os.listdir(path))
    except OSError:
        return False


def _directory_node(name, rel, info, children):
    """Build the tree node for a directory.

    ``children`` is the nested list for ``build_tree`` and ``None`` for the lazy
    endpoint, where children are fetched on expansion.
    """
    return {
        'name': name,
        'type': 'directory',
        'path': rel,
        'children': children,
        'created': info.st_ctime,
        'modified': info.st_mtime,
        'size': 0,
    }


def _aggregate(entries):
    """Count the direct children of a directory.

    ``file_size`` is the size of that folder's own files, not a recursive
    total: a recursive total needs every descendant listed, which is exactly
    what lazy loading avoids.
    """
    folder_count = 0
    file_count = 0
    file_size = 0
    for _entry, _full, _rel, info, is_directory in entries:
        if is_directory:
            folder_count += 1
        else:
            file_count += 1
            file_size += info.st_size
    return folder_count, file_count, file_size


def build_tree(current_path, relative_path, music_root):
    """Recursively list *current_path* as a nested tree."""
    items = []
    for entry, full, rel, info, is_directory in _scan_entries(
        current_path, relative_path, music_root
    ):
        if is_directory:
            children = build_tree(full, rel, music_root)
            node = _directory_node(entry, rel, info, children)
            node['folder_count'], node['file_count'], node['file_size'] = (
                _aggregate(_scan_entries(full, rel, music_root))
            )
            items.append(node)
        else:
            items.append(_classify_file(entry, rel, info))
    return items


def build_directory(current_path, relative_path, music_root):
    """List a single directory for the lazy tree endpoint.

    Returns the folder's own path, its entries and its direct-child counts.
    Directory entries carry ``children: None`` plus ``has_children`` so the
    client knows whether expanding is worthwhile before it fetches anything.
    """
    entries = _scan_entries(current_path, relative_path, music_root)
    items = []
    for entry, _full, rel, info, is_directory in entries:
        if is_directory:
            node = _directory_node(entry, rel, info, None)
            node['has_children'] = _dir_has_children(os.path.join(
                current_path, entry
            ))
            items.append(node)
        else:
            items.append(_classify_file(entry, rel, info))

    folder_count, file_count, file_size = _aggregate(entries)
    return {
        'path': relative_path.replace('\\', '/'),
        'entries': items,
        'folder_count': folder_count,
        'file_count': file_count,
        'file_size': file_size,
    }
