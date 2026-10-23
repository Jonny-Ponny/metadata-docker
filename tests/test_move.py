"""Move guardrails for the file tree (B-06)."""

from pathlib import Path


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def test_move_cannot_move_a_folder_into_itself(
    client, auth_headers, music_root, test_dir
):
    album = test_dir / "album"
    subfolder = album / "sub"
    subfolder.mkdir(parents=True)

    response = client.post(
        "/api/move",
        headers=auth_headers,
        json={
            "source": _relative(album, music_root),
            "destination": _relative(subfolder, music_root),
        },
    )

    assert response.status_code == 400
    assert album.is_dir()


def test_move_rejects_a_symlink_alias_into_the_same_folder(
    client, auth_headers, music_root, test_dir
):
    album = test_dir / "album"
    subfolder = album / "sub"
    subfolder.mkdir(parents=True)
    alias = test_dir / "alias"
    alias.symlink_to(album)

    response = client.post(
        "/api/move",
        headers=auth_headers,
        json={
            "source": _relative(album, music_root),
            "destination": _relative(alias / "sub", music_root),
        },
    )

    assert response.status_code == 400
    assert album.is_dir()


def test_move_still_moves_a_file(client, auth_headers, music_root, test_dir):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    destination = test_dir / "destination"
    destination.mkdir()

    response = client.post(
        "/api/move",
        headers=auth_headers,
        json={
            "source": _relative(song, music_root),
            "destination": _relative(destination, music_root),
        },
    )

    assert response.status_code == 200
    assert not song.exists()
    assert (destination / "song.mp3").read_bytes() == b"audio"
