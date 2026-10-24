"""The audio format registry is the single source of truth for extensions."""

import json

from formats import (
    FORMATS,
    IMAGE_EXTENSIONS,
    IMAGE_MIME_TYPES,
    SUPPORTED_EXTENSIONS,
    TEXT_EXTENSIONS,
    formats_info,
    get_extension,
    get_format,
    image_mime_for,
    is_supported_audio,
    mime_for,
)


def test_extensions_are_unique_and_lower_case():
    extensions = [
        extension for audio_format in FORMATS for extension in audio_format.extensions
    ]

    assert len(extensions) == len(set(extensions))
    assert SUPPORTED_EXTENSIONS == tuple(extensions)
    assert all(extension.startswith(".") for extension in extensions)
    assert all(extension == extension.lower() for extension in extensions)


def test_every_registered_family_has_a_backend():
    from tag_backends import (
        FLAC_BACKEND,
        ID3_BACKEND,
        MP4_BACKEND,
        VORBIS_BACKEND,
    )

    assert {audio_format.family for audio_format in FORMATS} == {
        "id3",
        "flac",
        "vorbis",
        "mp4",
    }
    assert all(
        backend is not None
        for backend in (ID3_BACKEND, FLAC_BACKEND, VORBIS_BACKEND, MP4_BACKEND)
    )


def test_every_format_has_a_mime_type():
    for audio_format in FORMATS:
        assert audio_format.mime
        assert audio_format.mime.startswith("audio/")
        assert audio_format.label


def test_lookup_is_case_insensitive():
    assert get_format("song.MP3").id == "mp3"
    assert get_format("album/Track.FlAc").id == "flac"
    assert is_supported_audio("track.OPUS")
    assert is_supported_audio("track.aif")
    assert not is_supported_audio("track.txt")
    assert get_format("track") is None


def test_extension_uses_the_last_suffix():
    assert get_extension("archive.tar.gz") == ".gz"
    assert get_extension("track.mp3") == ".mp3"
    assert get_extension("no-extension") == ""


def test_mime_for_uses_the_registry_and_a_default():
    assert mime_for("song.flac") == "audio/flac"
    assert mime_for("notes.txt") == "application/octet-stream"
    assert mime_for("notes.txt", default="text/plain") == "text/plain"


def test_formats_info_is_serialisable_json():
    info = formats_info()

    assert len(info) == len(FORMATS)
    assert json.loads(json.dumps(info)) == info
    assert {entry["id"] for entry in info} == {
        audio_format.id for audio_format in FORMATS
    }


def test_image_and_text_types_share_one_registry():
    assert IMAGE_EXTENSIONS == tuple(IMAGE_MIME_TYPES)
    assert image_mime_for("cover.PNG") == "image/png"
    assert image_mime_for("photo.JPEG") == "image/jpeg"
    assert image_mime_for("song.mp3") is None
    assert image_mime_for("notes.txt") is None
    assert TEXT_EXTENSIONS == (".txt", ".lrc")
