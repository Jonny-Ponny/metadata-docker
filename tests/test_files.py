"""File-tree classification and copy/delete/symlink behaviour."""

import os
from pathlib import Path


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _find_node(items, name):
    for item in items:
        if item["name"] == name:
            return item
        found = _find_node(item.get("children") or [], name)
        if found:
            return found
    return None


def test_build_tree_classifies_every_file_type(app_module, test_dir):
    for name in (
        "track.mp3",
        "cover.PNG",
        "lyrics.lrc",
        "notes.txt",
        "archive.zip",
    ):
        (test_dir / name).write_bytes(b"data")
    nested = test_dir / "album"
    nested.mkdir()
    (nested / "child.flac").write_bytes(b"audio")

    tree = app_module.build_tree(str(test_dir), test_dir.name)

    by_name = {item["name"]: item for item in tree}
    assert by_name["track.mp3"]["file_type"] == "audio"
    assert by_name["cover.PNG"]["file_type"] == "image"
    assert by_name["lyrics.lrc"]["file_type"] == "text"
    assert by_name["notes.txt"]["file_type"] == "text"
    assert by_name["archive.zip"]["file_type"] == "other"

    album = by_name["album"]
    assert album["type"] == "directory"
    assert album["path"] == f"{test_dir.name}/album"
    assert album["children"][0]["file_type"] == "audio"
    assert album["children"][0]["path"] == f"{test_dir.name}/album/child.flac"


def test_file_tree_lists_the_same_classification(
    client, auth_headers, test_dir
):
    (test_dir / "track.mp3").write_bytes(b"audio")
    (test_dir / "cover.jpg").write_bytes(b"image")
    (test_dir / "notes.txt").write_bytes(b"text")
    (test_dir / "readme.pdf").write_bytes(b"other")

    response = client.get("/api/files", headers=auth_headers)

    assert response.status_code == 200
    node = _find_node(response.get_json(), test_dir.name)
    files = {
        item["name"]: item["file_type"]
        for item in node["children"]
        if item["type"] == "file"
    }
    assert files == {
        "track.mp3": "audio",
        "cover.jpg": "image",
        "notes.txt": "text",
        "readme.pdf": "other",
    }


def test_file_tree_hides_in_progress_uploads(app_module, test_dir):
    (test_dir / ".upload-1234abcd.part").write_bytes(b"partial")
    (test_dir / ".hidden-but-complete").write_bytes(b"visible")

    names = [
        item["name"]
        for item in app_module.build_tree(str(test_dir), test_dir.name)
    ]

    assert ".upload-1234abcd.part" not in names
    assert ".hidden-but-complete" in names


def test_file_tree_skips_symlinked_directories(app_module, test_dir):
    album = test_dir / "album"
    album.mkdir()
    (album / "track.mp3").write_bytes(b"audio")
    (test_dir / "link-to-album").symlink_to(album)

    tree = app_module.build_tree(str(test_dir), test_dir.name)

    assert [item["name"] for item in tree] == ["album"]


def test_file_tree_lists_only_symlinks_that_resolve_inside(
    app_module, test_dir, tmp_path
):
    inside = test_dir / "inside.mp3"
    inside.write_bytes(b"audio")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")

    (test_dir / "inside-link.mp3").symlink_to(inside)
    (test_dir / "outside-link.mp3").symlink_to(outside)

    names = [
        item["name"]
        for item in app_module.build_tree(str(test_dir), test_dir.name)
    ]

    assert "inside-link.mp3" in names
    assert "outside-link.mp3" not in names


def test_build_tree_returns_empty_on_permission_error(
    app_module, test_dir, monkeypatch
):
    (test_dir / "track.mp3").write_bytes(b"audio")
    real_listdir = app_module.os.listdir

    def denied(path):
        if os.fspath(path) == str(test_dir):
            raise PermissionError(path)
        return real_listdir(path)

    monkeypatch.setattr(app_module.os, "listdir", denied)

    assert app_module.build_tree(str(test_dir), test_dir.name) == []


def test_copy_file_uses_copy_suffixes(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    relative = _relative(song, music_root)

    assert client.post(
        "/api/copy", headers=auth_headers, json={"path": relative}
    ).status_code == 200
    assert client.post(
        "/api/copy", headers=auth_headers, json={"path": relative}
    ).status_code == 200

    assert (test_dir / "song - Copy.mp3").read_bytes() == b"audio"
    assert (test_dir / "song - Copy(1).mp3").read_bytes() == b"audio"


def test_copy_folder_preserves_symlinks_instead_of_following_them(
    client, auth_headers, test_dir, music_root, tmp_path
):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    album = test_dir / "album"
    album.mkdir()
    (album / "song.mp3").write_bytes(b"audio")
    (album / "link.mp3").symlink_to(outside)

    response = client.post(
        "/api/copy",
        headers=auth_headers,
        json={"path": _relative(album, music_root)},
    )

    assert response.status_code == 200
    copied = test_dir / "album - Copy"
    assert copied.is_dir()
    assert (copied / "song.mp3").read_bytes() == b"audio"
    assert (copied / "link.mp3").is_symlink()
    assert os.readlink(copied / "link.mp3") == str(outside)
    assert outside.read_bytes() == b"secret"


def test_copy_folder_uses_copy_suffixes(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "album"
    album.mkdir()
    (album / "song.mp3").write_bytes(b"audio")
    relative = _relative(album, music_root)

    assert client.post(
        "/api/copy", headers=auth_headers, json={"path": relative}
    ).status_code == 200
    assert client.post(
        "/api/copy", headers=auth_headers, json={"path": relative}
    ).status_code == 200

    assert (test_dir / "album - Copy").is_dir()
    assert (test_dir / "album - Copy (1)").is_dir()


def test_delete_removes_an_inside_symlink_without_the_target(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    link = test_dir / "link.mp3"
    link.symlink_to(song)

    response = client.post(
        "/api/delete",
        headers=auth_headers,
        json={"path": _relative(link, music_root)},
    )

    assert response.status_code == 200
    assert not os.path.lexists(link)
    assert song.read_bytes() == b"audio"


def test_delete_never_follows_a_symlink_outside_the_library(
    client, auth_headers, test_dir, music_root, tmp_path
):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    link = test_dir / "outside-link.mp3"
    link.symlink_to(outside)

    response = client.post(
        "/api/delete",
        headers=auth_headers,
        json={"path": _relative(link, music_root)},
    )

    assert response.status_code == 403
    assert link.is_symlink()
    assert outside.read_bytes() == b"secret"
