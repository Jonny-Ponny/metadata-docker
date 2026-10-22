"""Read metadata from a supported audio file.

All format-specific work lives in ``tag_backends``. This module only loads the
file with mutagen and hands it to the matching backend.
"""

from mutagen import File

from formats import get_extension
from tag_backends import backend_for, empty_metadata


def extract_metadata(filepath, include_picture=True):
    """Return the canonical metadata payload for *filepath*, or None."""
    audio = File(filepath, easy=False)
    if audio is None:
        return None

    backend = backend_for(audio)
    if backend is None:
        return None

    return backend.extract(audio, include_picture=include_picture)


def read_only_metadata(filepath):
    """Return an empty payload that tells the UI the file is read-only.

    Unsupported files are still listed in the tree so they can be inspected,
    renamed, downloaded or deleted. They must not be presented as editable
    though, because no tag backend can write them.
    """
    result = empty_metadata()
    result['readOnly'] = True
    result['supported'] = False
    result['format'] = get_extension(filepath).lstrip('.').upper() or 'Unknown'
    return result
