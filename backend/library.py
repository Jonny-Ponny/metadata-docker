"""File-tree classification and natural sorting for the library listing.

``build_tree`` takes the library root as a parameter (like the helpers in
``paths.py``) so it can be unit-tested against a temporary directory without
importing the Flask app.
"""

import os
import re

from formats import is_supported_audio
from paths import is_within

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
TEXT_EXTENSIONS = ('.txt', '.lrc')


def natural_key(text):
    """Convert text into a list of strings and numbers for natural sorting.

    ``str.isdigit()`` is true for characters such as ``²`` that ``int()``
    rejects, so only ASCII digits are converted (B-10).
    """
    return [
        int(part) if part.isascii() and part.isdigit() else part.lower()
        for part in re.split(r'(\d+)', text)
    ]


def build_tree(current_path, relative_path, music_root):
    items = []
    try:
        entries = sorted(os.listdir(current_path), key=natural_key)
        for entry in entries:
            # Uploads are written to a hidden .upload-*.part file and renamed
            # into place, so a tree reload during a long upload must not list
            # the temporary file. Other dotfiles stay visible.
            if entry.startswith('.upload-') and entry.endswith('.part'):
                continue
            full = os.path.join(current_path, entry)
            rel = os.path.join(relative_path, entry).replace('\\', '/')
            # An entry can disappear between listdir() and stat() when a file
            # is deleted or renamed concurrently. Skip it instead of failing
            # the whole tree with a 500 (B-11).
            if os.path.isdir(full):
                # Symlinked directories are skipped: following them can escape
                # the library root or recurse forever through a cycle.
                # safe_path() resolves symlinks as well, so anything not listed
                # here could not be opened through the API either.
                if os.path.islink(full):
                    continue
                try:
                    children = build_tree(full, rel, music_root)
                    info = os.stat(full)
                except OSError:
                    continue
                items.append({
                    'name': entry,
                    'type': 'directory',
                    'path': rel,
                    'children': children,
                    'created': info.st_ctime,
                    'modified': info.st_mtime,
                    'size': 0
                })
            elif os.path.isfile(full):
                # A symlinked file is only listed when it resolves inside the
                # library. This also avoids calling os.stat() on a link that
                # points at an arbitrary outside file.
                if os.path.islink(full) and not is_within(music_root, full):
                    continue
                try:
                    info = os.stat(full)
                except OSError:
                    continue
                # Check for audio files
                if is_supported_audio(entry):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'audio',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })
                # Check for image files
                elif entry.lower().endswith(IMAGE_EXTENSIONS):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'image',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })

                elif entry.lower().endswith(TEXT_EXTENSIONS):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'text',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })
                # Everything else is still listed so it can be inspected,
                # renamed, downloaded or deleted. The metadata endpoint marks
                # these files read-only.
                else:
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'file_type': 'other',
                        'path': rel,
                        'size': info.st_size,
                        'created': info.st_ctime,
                        'modified': info.st_mtime
                    })

    except PermissionError:
        pass

    return items
