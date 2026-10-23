"""Tag and cover-art round-trips for every supported format."""

import pytest

from formats import FORMATS, SUPPORTED_EXTENSIONS
from metadata_extractor import extract_metadata, read_only_metadata
from metadata_writer import (
    delete_cover_art,
    delete_metadata_field,
    update_file_metadata,
    update_file_picture,
)
from tag_backends import FIELD_SCHEMA, empty_metadata


# One value per canonical field. Dates, numbers and LRC text are deliberately
# realistic because the backends convert them (MP4 number pairs, SYLT events).
FIELD_VALUES = {
    "title": "Title Value",
    "album": "Album Value",
    "artist": "Artist Value",
    "albumArtist": "Album Artist",
    "trackNumber": "3",
    "diskNumber": "2",
    "date": "2024-05-01",
    "genre": "Rock",
    "comment": "A comment",
    "description": "A description",
    "composer": "Composer Name",
    "publisher": "Publisher Name",
    "releaseType": "Album",
    "lyrics": "[00:12.00] First line\n[01:02.50] Second line",
    "unsyncedLyrics": "Plain line one\nPlain line two",
}

COVER_BYTES = {
    "image/jpeg": b"\xff\xd8\xff\xe0" + b"jpeg-cover",
    "image/png": b"\x89PNG\r\n\x1a\n" + b"png-cover",
    "image/gif": b"GIF89a" + b"gif-cover",
    "image/bmp": b"BM" + b"bmp-cover",
    "image/webp": b"RIFF" + (4).to_bytes(4, "little") + b"WEBP" + b"webp-cover",
}

BACKEND_EXTENSIONS = {
    "id3": (".mp3", ".wav", ".aiff", ".aif"),
    "flac": (".flac",),
    "vorbis": (".ogg", ".oga", ".opus"),
    "mp4": (".m4a", ".m4b"),
}


def test_field_schema_matches_the_empty_payload():
    assert set(FIELD_SCHEMA) == set(empty_metadata()) - {"customFields"}
    assert set(FIELD_VALUES) == set(FIELD_SCHEMA)


def test_formats_registry_covers_every_backend_family():
    extensions = {
        extension for values in BACKEND_EXTENSIONS.values() for extension in values
    }
    assert extensions == set(SUPPORTED_EXTENSIONS)
    assert {audio_format.family for audio_format in FORMATS} == set(
        BACKEND_EXTENSIONS
    )


def test_read_only_metadata_shape(app_module, tmp_path):
    result = read_only_metadata(tmp_path / "notes.pdf")

    assert result["readOnly"] is True
    assert result["supported"] is False
    assert result["format"] == "PDF"
    assert result["customFields"] == []
    assert set(result) >= set(FIELD_SCHEMA)


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
@pytest.mark.parametrize("field", FIELD_SCHEMA)
def test_field_round_trip(audio_file, extension, field):
    path = audio_file(extension)
    value = FIELD_VALUES[field]

    assert update_file_metadata(path, field, value) is True
    metadata = extract_metadata(path)

    assert metadata is not None
    assert metadata[field] == value, (extension, field)


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_fields_coexist_on_one_file(audio_file, extension):
    path = audio_file(extension)

    for field, value in FIELD_VALUES.items():
        assert update_file_metadata(path, field, value) is True

    metadata = extract_metadata(path)

    assert metadata is not None
    for field, value in FIELD_VALUES.items():
        assert metadata[field] == value, (extension, field)


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_comment_description_and_custom_fields_are_distinct(
    audio_file, extension
):
    path = audio_file(extension)

    assert update_file_metadata(path, "comment", "The comment")
    assert update_file_metadata(path, "description", "The description")
    assert update_file_metadata(path, "mood", "Calm")

    metadata = extract_metadata(path)

    assert metadata["comment"] == "The comment"
    assert metadata["description"] == "The description"
    assert {"name": "mood", "value": "Calm"} in metadata["customFields"]


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_delete_field_clears_only_that_field(audio_file, extension):
    path = audio_file(extension)
    assert update_file_metadata(path, "title", "Keep me")
    assert update_file_metadata(path, "album", "Delete me")

    assert delete_metadata_field(path, "album") is True
    metadata = extract_metadata(path)

    assert metadata["title"] == "Keep me"
    assert metadata["album"] == ""


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_delete_custom_field(audio_file, extension):
    path = audio_file(extension)
    assert update_file_metadata(path, "mood", "Calm")

    assert delete_metadata_field(path, "mood") is True
    metadata = extract_metadata(path)

    # The fixtures carry encoder tags (for example ©too), which are exposed as
    # custom fields too; only the user field must be gone.
    assert all(
        custom["name"].casefold() != "mood"
        for custom in metadata["customFields"]
    )


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_cover_art_round_trip_and_delete(audio_file, extension):
    path = audio_file(extension)
    image = COVER_BYTES["image/jpeg"]

    assert update_file_picture(path, image, "image/jpeg") is True

    metadata = extract_metadata(path)
    assert metadata["picture"].startswith("data:image/jpeg;base64,")
    assert metadata["picture"].split(",", 1)[1]

    metadata_without_picture = extract_metadata(path, include_picture=False)
    assert metadata_without_picture["hasPicture"] is True
    assert "picture" not in metadata_without_picture

    assert delete_cover_art(path) is True
    metadata = extract_metadata(path)
    assert "picture" not in metadata
    assert "hasPicture" not in metadata


@pytest.mark.parametrize(
    "extension",
    [
        extension
        for family, extensions in BACKEND_EXTENSIONS.items()
        if family != "mp4"
        for extension in extensions
    ],
)
@pytest.mark.parametrize("mime", sorted(COVER_BYTES))
def test_cover_mime_is_detected_from_the_bytes(audio_file, extension, mime):
    path = audio_file(extension)
    image = COVER_BYTES[mime]

    # The client MIME is deliberately wrong; the magic bytes must win.
    assert update_file_picture(path, image, "image/jpeg") is True

    metadata = extract_metadata(path)
    assert metadata["picture"].startswith(f"data:{mime};base64,")


@pytest.mark.parametrize("extension", BACKEND_EXTENSIONS["mp4"])
def test_mp4_cover_round_trips_png(audio_file, extension):
    path = audio_file(extension)
    image = COVER_BYTES["image/png"]

    assert update_file_picture(path, image, "image/png") is True

    metadata = extract_metadata(path)
    assert metadata["picture"].startswith("data:image/png;base64,")


def test_synced_lyrics_are_only_stored_as_sylt_for_id3(audio_file):
    """The ID3 backend converts LRC to SYLT; the others keep the text."""
    lrc = "[0:12.34] Short minutes\n[00:12.345] Three decimals"

    id3_file = audio_file(".mp3")
    assert update_file_metadata(id3_file, "lyrics", lrc)
    # LRC is normalised to centiseconds when read back from SYLT.
    assert extract_metadata(id3_file)["lyrics"] == (
        "[00:12.34] Short minutes\n[00:12.34] Three decimals"
    )

    vorbis_file = audio_file(".ogg")
    assert update_file_metadata(vorbis_file, "lyrics", lrc)
    assert extract_metadata(vorbis_file)["lyrics"] == lrc
