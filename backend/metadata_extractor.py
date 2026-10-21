"""Read metadata from a supported audio file.

All format-specific work lives in ``tag_backends``. This module only loads the
file with mutagen and hands it to the matching backend.
"""

from mutagen import File

from tag_backends import backend_for


def extract_metadata(filepath, include_picture=True):
    """Return the canonical metadata payload for *filepath*, or None."""
    audio = File(filepath, easy=False)
    if audio is None:
        return None

    backend = backend_for(audio)
    if backend is None:
        return None

    return backend.extract(audio, include_picture=include_picture)
