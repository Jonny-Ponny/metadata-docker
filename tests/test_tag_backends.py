"""Cover MIME detection and LRC parsing (B-22, B-23)."""

import pytest

import tag_backends


IMAGE_CASES = [
    (b"\xff\xd8\xff\xe0" + b"0" * 8, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n" + b"0" * 8, "image/png"),
    (b"GIF87a" + b"0" * 8, "image/gif"),
    (b"GIF89a" + b"0" * 8, "image/gif"),
    (b"BM" + b"0" * 10, "image/bmp"),
    (b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 8, "image/webp"),
]


@pytest.mark.parametrize("data,expected", IMAGE_CASES)
def test_detect_image_mime_reads_magic_bytes(data, expected):
    assert tag_backends.detect_image_mime(data) == expected


def test_detect_image_mime_returns_none_for_unknown_data():
    assert tag_backends.detect_image_mime(b"not an image") is None


def test_resolve_image_mime_prefers_bytes_over_client_type():
    assert (
        tag_backends.resolve_image_mime(b"GIF89a", "image/jpeg")
        == "image/gif"
    )


def test_resolve_image_mime_falls_back_to_client_type():
    assert (
        tag_backends.resolve_image_mime(b"unknown", "image/avif")
        == "image/avif"
    )


def test_resolve_image_mime_rejects_unknown_data_without_a_type():
    assert (
        tag_backends.resolve_image_mime(b"unknown")
        == "application/octet-stream"
    )


@pytest.mark.parametrize(
    "line,expected",
    [
        ("[0:12.34] hello", [("hello", 12340)]),
        ("[00:12.345] hello", [("hello", 12345)]),
        ("[1:02.5] hello", [("hello", 62500)]),
        ("[01:02] hello", [("hello", 62000)]),
        ("no timestamp", []),
    ],
)
def test_lrc_timestamps_accept_the_common_subset(line, expected):
    assert tag_backends.lrc_to_sylt_events(line) == expected


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        (12340, "[00:12.34]"),
        (59999, "[01:00.00]"),
        (60000, "[01:00.00]"),
    ],
)
def test_sylt_timestamps_carry_into_the_next_minute(timestamp, expected):
    assert tag_backends.format_sylt_timestamp(timestamp) == expected


def test_sylt_timestamp_with_a_sample_rate():
    assert tag_backends.format_sylt_timestamp(22050, 44100) == "[00:00.50]"
