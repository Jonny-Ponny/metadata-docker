"""The lazy per-directory tree endpoint and its direct-child aggregates."""

import os


def _relative(path, music_root):
    from pathlib import Path

    return Path(path).relative_to(music_root).as_posix()


def _names(entries):
    return [entry["name"] for entry in entries]


def test_directory_lists_one_level_and_classifies_files(
    client, auth_headers, test_dir, music_root
):
    for name in ("track.mp3", "cover.PNG", "lyrics.lrc", "archive.zip"):
        (test_dir / name).write_bytes(b"data")
    album = test_dir / "album"
    album.mkdir()
    (album / "child.flac").write_bytes(b"audio")

    response = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir, music_root)},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["path"] == _relative(test_dir, music_root)
    assert _names(body["entries"]) == [
        "album",
        "archive.zip",
        "cover.PNG",
        "lyrics.lrc",
        "track.mp3",
    ]
    by_name = {entry["name"]: entry for entry in body["entries"]}
    assert by_name["track.mp3"]["file_type"] == "audio"
    assert by_name["cover.PNG"]["file_type"] == "image"
    assert by_name["lyrics.lrc"]["file_type"] == "text"
    assert by_name["archive.zip"]["file_type"] == "other"


def test_directory_folders_are_not_expanded_on_fetch(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "album"
    album.mkdir()
    (album / "child.flac").write_bytes(b"audio")
    empty = test_dir / "empty"
    empty.mkdir()

    body = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir, music_root)},
    ).get_json()

    by_name = {entry["name"]: entry for entry in body["entries"]}
    assert by_name["album"]["children"] is None
    assert by_name["album"]["has_children"] is True
    assert by_name["empty"]["has_children"] is False


def test_directory_reports_direct_child_aggregates(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "a.mp3").write_bytes(b"1234")
    (test_dir / "b.mp3").write_bytes(b"12")
    album = test_dir / "album"
    album.mkdir()
    (album / "nested.flac").write_bytes(b"nested")

    body = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir, music_root)},
    ).get_json()

    # One folder, two files, six bytes of files directly in this folder. The
    # nested file is deliberately not counted: sizes are per level so the
    # response never needs to walk the whole library.
    assert body["folder_count"] == 1
    assert body["file_count"] == 2
    assert body["file_size"] == 6

    root = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": ""},
    ).get_json()
    assert root["path"] == ""


def test_directory_hides_in_progress_uploads_and_outside_symlinks(
    client, auth_headers, test_dir, music_root, tmp_path
):
    (test_dir / ".upload-1234abcd.part").write_bytes(b"partial")
    (test_dir / "keep.mp3").write_bytes(b"audio")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    os.symlink(outside, test_dir / "link.mp3")

    body = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir, music_root)},
    ).get_json()

    assert _names(body["entries"]) == ["keep.mp3"]


def test_directory_sorts_naturally(client, auth_headers, test_dir, music_root):
    for name in ("a10.mp3", "a2.mp3", "a².mp3"):
        (test_dir / name).write_bytes(b"audio")

    body = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir, music_root)},
    ).get_json()

    assert _names(body["entries"]) == ["a2.mp3", "a10.mp3", "a².mp3"]


def test_directory_rejects_a_missing_folder(
    client, auth_headers, music_root
):
    response = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": "does-not-exist"},
    )

    assert response.status_code == 404


def test_directory_rejects_a_file_path(client, auth_headers, test_dir, music_root):
    (test_dir / "track.mp3").write_bytes(b"audio")

    response = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir / "track.mp3", music_root)},
    )

    assert response.status_code == 400


def test_directory_rejects_a_path_outside_the_library(client, auth_headers):
    response = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": "../../etc"},
    )

    assert response.status_code == 403


def test_directory_treats_a_vanished_folder_as_empty(
    client, auth_headers, test_dir, music_root, monkeypatch
):
    """A folder deleted between the request and listdir() returns no entries."""

    import library

    monkeypatch.setattr(library, "_listdir_names", lambda path: [])

    response = client.get(
        "/api/files/dir",
        headers=auth_headers,
        query_string={"path": _relative(test_dir, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()["entries"] == []


def test_directory_reports_unexpected_failures(
    client, auth_headers, files_module, music_root, monkeypatch
):
    def broken(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(files_module.library, "build_directory", broken)

    response = client.get(
        "/api/files/dir", headers=auth_headers, query_string={"path": ""}
    )

    assert response.status_code == 500
