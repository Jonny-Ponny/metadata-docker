"""Single source of truth for the audio formats this app can read and write.

Add a new format here first, then register a backend for its family in
``tag_backends.py``. Everything else (file tree, API validation, MIME types)
is derived from this registry.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    """A supported audio format.

    ``family`` identifies the tag implementation in ``tag_backends.py``.
    Several extensions can share one family (FLAC and OGG both use Vorbis
    comments, for example).
    """

    id: str
    label: str
    extensions: tuple
    mime: str
    family: str


FORMATS = (
    AudioFormat('mp3', 'MP3', ('.mp3',), 'audio/mpeg', 'id3'),
    AudioFormat('wav', 'WAV', ('.wav',), 'audio/wav', 'id3'),
    AudioFormat('aiff', 'AIFF', ('.aiff', '.aif'), 'audio/aiff', 'id3'),
    AudioFormat('flac', 'FLAC', ('.flac',), 'audio/flac', 'flac'),
    AudioFormat('ogg', 'OGG Vorbis', ('.ogg', '.oga'), 'audio/ogg', 'vorbis'),
    AudioFormat('opus', 'Opus', ('.opus',), 'audio/ogg', 'vorbis'),
    AudioFormat('m4a', 'M4A', ('.m4a',), 'audio/mp4', 'mp4'),
    AudioFormat('m4b', 'M4B', ('.m4b',), 'audio/mp4', 'mp4'),
)

# extension -> AudioFormat
_BY_EXTENSION = {
    extension: audio_format
    for audio_format in FORMATS
    for extension in audio_format.extensions
}

SUPPORTED_EXTENSIONS = tuple(_BY_EXTENSION)

# The image and text types the tree lists and the API serves. Keeping the MIME
# map next to the audio registry means `/api/image`, downloads and `build_tree`
# cannot disagree about which files count as images.
IMAGE_MIME_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp',
    '.webp': 'image/webp',
}

IMAGE_EXTENSIONS = tuple(IMAGE_MIME_TYPES)

TEXT_EXTENSIONS = ('.txt', '.lrc')


def image_mime_for(path):
    """Return the image MIME type for *path*, or None for a non-image."""
    return IMAGE_MIME_TYPES.get(get_extension(path))


def get_extension(path):
    """Return a lower-case extension including the leading dot."""
    return os.path.splitext(str(path))[1].lower()


def get_format(path):
    """Return the AudioFormat for *path*, or None when unsupported."""
    return _BY_EXTENSION.get(get_extension(path))


def is_supported_audio(path):
    """True when *path* has an extension handled by the metadata backends."""
    return get_format(path) is not None


def mime_for(path, default='application/octet-stream'):
    """Return the MIME type registered for *path*."""
    audio_format = get_format(path)
    return audio_format.mime if audio_format else default


def formats_info():
    """Serialisable format list, used by the API and tests."""
    return [
        {
            'id': audio_format.id,
            'label': audio_format.label,
            'extensions': list(audio_format.extensions),
            'mime': audio_format.mime,
            'family': audio_format.family,
        }
        for audio_format in FORMATS
    ]
