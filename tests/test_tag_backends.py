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


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", None),
        ("3", (3, 0)),
        ("3/12", (3, 12)),
        (" 3 / 12 ", (3, 12)),
        ("abc/12", (0, 12)),
        ("-5/70000", (0, 65535)),
    ],
)
def test_parse_number_pair(value, expected):
    assert tag_backends.parse_number_pair(value) == expected


@pytest.mark.parametrize(
    "values,expected",
    [
        ([], ""),
        ([(0, 0)], ""),
        ([(3, 0)], "3"),
        ([(3, 12)], "3/12"),
        ([("bad",)], ""),
    ],
)
def test_format_number_pair(values, expected):
    assert tag_backends.format_number_pair(values) == expected


@pytest.mark.parametrize(
    "key,expected",
    [
        ("----:com.apple.iTunes:MY_FIELD", "MY_FIELD"),
        ("TIT2", "TIT2"),
        ("----:broken", ""),
    ],
)
def test_mp4_freeform_name(key, expected):
    assert tag_backends.mp4_freeform_name(key) == expected


def test_decode_freeform_values_joins_and_survives_invalid_bytes():
    assert tag_backends.decode_freeform_values([b"one", b"two"]) == "one; two"
    assert tag_backends.decode_freeform_values([b"\xff"]) == "b'\\xff'"


@pytest.mark.parametrize(
    "first,second",
    [
        ("Release Type", "releasetype"),
        ("release_type", "RELEASE-TYPE"),
        ("release type", "release_type"),
    ],
)
def test_field_names_are_normalised(first, second):
    assert tag_backends._normalise_field_name(first) == (
        tag_backends._normalise_field_name(second)
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
