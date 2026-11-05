"""Recursive folder totals for the tree tooltip (/api/files/summary)."""

import os
from pathlib import Path


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _summary(client, auth_headers, music_root, path=""):
    return client.get(
        "/api/files/summary",
        headers=auth_headers,
        query_string={"path": _relative(path, music_root) if path else ""},
    )


def test_summary_totals_the_whole_subtree(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "loose.mp3").write_bytes(b"1234")
    album = test_dir / "album"
    album.mkdir()
    (album / "a.flac").write_bytes(b"12")
    disc = album / "disc2"
    disc.mkdir()
    (disc / "b.flac").write_bytes(b"1")
    (disc / "cover.jpg").write_bytes(b"123")

    response = _summary(client, auth_headers, music_root, album)

    assert response.status_code == 200
    assert response.get_json() == {
        "path": _relative(album, music_root),
        "folder_count": 1,
        "file_count": 3,
        "file_size": 6,
        "format_counts": {"FLAC": 2, "JPG": 1},
    }


def test_summary_does_not_count_siblings(
    client, auth_headers, test_dir, music_root
):
    """A folder's total covers its subtree only, never its siblings."""
    wanted = test_dir / "wanted"
    wanted.mkdir()
    (wanted / "a.mp3").write_bytes(b"12")
    other = test_dir / "other"
    other.mkdir()
    (other / "b.mp3").write_bytes(b"123456")
    (test_dir / "loose.mp3").write_bytes(b"1")

    body = _summary(client, auth_headers, music_root, wanted).get_json()

    assert body["file_count"] == 1
    assert body["file_size"] == 2
    assert body["folder_count"] == 0


def test_summary_of_an_empty_folder(
    client, auth_headers, test_dir, music_root
):
    response = _summary(client, auth_headers, music_root, test_dir)

    assert response.status_code == 200
    body = response.get_json()
    assert body["folder_count"] == 0
    assert body["file_count"] == 0
    assert body["file_size"] == 0
    assert body["format_counts"] == {}


def test_summary_labels_files_without_an_extension(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "README").write_bytes(b"x")
    (test_dir / "song.MP3").write_bytes(b"xy")

    body = _summary(client, auth_headers, music_root, test_dir).get_json()

    assert body["format_counts"] == {"UNKNOWN": 1, "MP3": 1}


def test_summary_uses_the_same_symlink_policy(
    client, auth_headers, test_dir, music_root, tmp_path
):
    (test_dir / "keep.mp3").write_bytes(b"audio")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    os.symlink(outside, test_dir / "link.mp3")
    # A symlinked directory must not be followed (cycles, escaping the root).
    (test_dir / "linked-dir").symlink_to(tmp_path)

    body = _summary(client, auth_headers, music_root, test_dir).get_json()

    assert body["file_count"] == 1
    assert body["file_size"] == 5
    assert body["folder_count"] == 0


def test_summary_hides_in_progress_uploads(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "song.mp3").write_bytes(b"audio")
    (test_dir / ".upload-1234.part").write_bytes(b"partial")

    body = _summary(client, auth_headers, music_root, test_dir).get_json()

    assert body["file_count"] == 1


def test_summary_rejects_a_missing_folder(client, auth_headers):
    response = client.get(
        "/api/files/summary",
        headers=auth_headers,
        query_string={"path": "does-not-exist"},
    )

    assert response.status_code == 404


def test_summary_rejects_a_file_path(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "track.mp3").write_bytes(b"audio")

    response = _summary(client, auth_headers, music_root, test_dir / "track.mp3")

    assert response.status_code == 400


def test_summary_rejects_a_path_outside_the_library(client, auth_headers):
    response = client.get(
        "/api/files/summary",
        headers=auth_headers,
        query_string={"path": "../../etc"},
    )

    assert response.status_code == 403


def test_summary_reports_unexpected_failures(
    client, auth_headers, files_module, music_root, monkeypatch
):
    def broken(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(files_module.library, "summarize_tree", broken)

    response = client.get(
        "/api/files/summary", headers=auth_headers, query_string={"path": ""}
    )

    assert response.status_code == 500
