"""Rename guardrails for the file tree (B-05)."""

from pathlib import Path


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def test_rename_cannot_overwrite_an_existing_file(
    client, auth_headers, music_root, test_dir
):
    source = test_dir / "a.mp3"
    source.write_bytes(b"source")
    target = test_dir / "b.mp3"
    target.write_bytes(b"target")

    response = client.post(
        "/api/rename",
        headers=auth_headers,
        json={"oldPath": _relative(source, music_root), "newName": "b.mp3"},
    )

    assert response.status_code == 409
    assert source.read_bytes() == b"source"
    assert target.read_bytes() == b"target"


def test_rename_to_the_same_name_is_a_noop(
    client, auth_headers, music_root, test_dir
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = client.post(
        "/api/rename",
        headers=auth_headers,
        json={"oldPath": _relative(song, music_root), "newName": "song.mp3"},
    )

    assert response.status_code == 200
    assert song.read_bytes() == b"audio"


def test_rename_still_renames(client, auth_headers, music_root, test_dir):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = client.post(
        "/api/rename",
        headers=auth_headers,
        json={"oldPath": _relative(song, music_root), "newName": "renamed.mp3"},
    )

    assert response.status_code == 200
    assert not song.exists()
    assert (test_dir / "renamed.mp3").read_bytes() == b"audio"
