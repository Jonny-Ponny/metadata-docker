"""Folder operations and the smart-rename route."""

import os
from pathlib import Path

import pytest

from metadata_writer import update_file_metadata


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _post(client, headers, route, **body):
    return client.post(route, headers=headers, json=body)


def test_delete_removes_a_folder_recursively(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "album"
    nested = album / "nested"
    nested.mkdir(parents=True)
    (album / "song.mp3").write_bytes(b"audio")
    (nested / "track.flac").write_bytes(b"audio")

    response = _post(
        client,
        auth_headers,
        "/api/delete",
        path=_relative(album, music_root),
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert not album.exists()
    assert test_dir.is_dir()


def test_delete_missing_path_is_404(client, auth_headers, music_root):
    response = _post(
        client,
        auth_headers,
        "/api/delete",
        path="does-not-exist.mp3",
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Path not found"


def test_delete_removes_a_broken_symlink(client, auth_headers, test_dir, music_root):
    target = test_dir / "target.mp3"
    target.write_bytes(b"audio")
    link = test_dir / "link.mp3"
    link.symlink_to(target)
    target.unlink()

    response = _post(
        client,
        auth_headers,
        "/api/delete",
        path=_relative(link, music_root),
    )

    assert response.status_code == 200
    assert not os.path.lexists(link)


def test_delete_removes_a_symlinked_directory_without_the_target(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "album"
    album.mkdir()
    (album / "song.mp3").write_bytes(b"audio")
    link = test_dir / "album-link"
    link.symlink_to(album, target_is_directory=True)

    response = _post(
        client,
        auth_headers,
        "/api/delete",
        path=_relative(link, music_root),
    )

    assert response.status_code == 200
    assert not os.path.lexists(link)
    assert (album / "song.mp3").exists()


def test_rename_a_file_and_a_folder(client, auth_headers, test_dir, music_root):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath=_relative(song, music_root),
        newName="renamed.mp3",
    )

    assert response.status_code == 200
    assert response.get_json()["newPath"] == _relative(
        test_dir / "renamed.mp3", music_root
    )
    assert (test_dir / "renamed.mp3").read_bytes() == b"audio"

    album = test_dir / "album"
    album.mkdir()
    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath=_relative(album, music_root),
        newName="renamed-album",
    )

    assert response.status_code == 200
    assert (test_dir / "renamed-album").is_dir()
    assert not album.exists()


def test_rename_missing_path_is_404(client, auth_headers, music_root):
    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath="missing.mp3",
        newName="other.mp3",
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Path not found"


@pytest.mark.parametrize(
    "new_name",
    [".", "..", "a/b.mp3", "a\\b.mp3", "nul\0.mp3", 123],
)
def test_rename_rejects_names_that_are_not_bare_filenames(
    client, auth_headers, test_dir, music_root, new_name
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath=_relative(song, music_root),
        newName=new_name,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid new name"
    assert song.exists()


def test_rename_cannot_move_the_library_root(client, auth_headers, music_root):
    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath=".",
        newName="renamed-library",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid new name"
    assert music_root.is_dir()


def test_rename_requires_both_names(client, auth_headers, music_root):
    response = _post(
        client, auth_headers, "/api/rename", oldPath="song.mp3"
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing oldPath or newName"


def test_move_a_file_and_a_folder(client, auth_headers, test_dir, music_root):
    source = test_dir / "source"
    source.mkdir()
    destination = test_dir / "destination"
    destination.mkdir()
    song = source / "song.mp3"
    song.write_bytes(b"audio")

    response = _post(
        client,
        auth_headers,
        "/api/move",
        source=_relative(song, music_root),
        destination=_relative(destination, music_root),
    )

    assert response.status_code == 200
    assert response.get_json()["newPath"] == _relative(
        destination / "song.mp3", music_root
    )
    assert not song.exists()

    album = source / "album"
    album.mkdir()
    response = _post(
        client,
        auth_headers,
        "/api/move",
        source=_relative(album, music_root),
        destination=_relative(destination, music_root),
    )

    assert response.status_code == 200
    assert (destination / "album").is_dir()
    assert not album.exists()


def test_move_to_the_library_root(client, auth_headers, test_dir, music_root):
    album = test_dir / "album"
    album.mkdir()
    song = album / "song.mp3"
    song.write_bytes(b"audio")

    response = _post(
        client,
        auth_headers,
        "/api/move",
        source=_relative(song, music_root),
        destination="",
    )

    assert response.status_code == 200
    assert (music_root / "song.mp3").read_bytes() == b"audio"


def test_move_missing_source_is_404(client, auth_headers, test_dir, music_root):
    response = _post(
        client,
        auth_headers,
        "/api/move",
        source="missing.mp3",
        destination=_relative(test_dir, music_root),
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Source not found"


def test_move_destination_must_be_a_folder(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    target = test_dir / "target"
    target.write_bytes(b"not a folder")

    response = _post(
        client,
        auth_headers,
        "/api/move",
        source=_relative(song, music_root),
        destination=_relative(target, music_root),
    )

    assert response.status_code == 400
    assert "not a directory" in response.get_json()["error"]


def test_move_does_not_overwrite_a_name_in_the_destination(
    client, auth_headers, test_dir, music_root
):
    source = test_dir / "source"
    source.mkdir()
    song = source / "song.mp3"
    song.write_bytes(b"source")
    destination = test_dir / "destination"
    destination.mkdir()
    (destination / "song.mp3").write_bytes(b"destination")

    response = _post(
        client,
        auth_headers,
        "/api/move",
        source=_relative(song, music_root),
        destination=_relative(destination, music_root),
    )

    assert response.status_code == 409
    assert (destination / "song.mp3").read_bytes() == b"destination"
    assert song.read_bytes() == b"source"


def _smart_rename(client, headers, path, music_root, **body):
    payload = {
        "path": _relative(path, music_root),
        "scheme": "[TITLE]",
        "isFolder": False,
        "replaceSpaces": False,
    }
    payload.update(body)
    return _post(client, headers, "/api/apply-renaming-scheme", **payload)


def test_smart_rename_file_uses_the_tag_value(
    client, auth_headers, audio_file, test_dir, music_root
):
    song = audio_file(".mp3", name="untitled.mp3")
    assert update_file_metadata(str(song), "title", "Real Title")

    response = _smart_rename(client, auth_headers, song, music_root)

    assert response.status_code == 200
    body = response.get_json()
    assert body["newName"] == "Real Title.mp3"
    assert body["newPath"] == _relative(test_dir / "Real Title.mp3", music_root)
    assert (test_dir / "Real Title.mp3").is_file()
    assert not song.exists()


def test_smart_rename_file_is_a_noop_when_the_name_matches(
    client, auth_headers, audio_file, test_dir, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    assert update_file_metadata(str(song), "title", "song")

    response = _smart_rename(client, auth_headers, song, music_root)

    assert response.status_code == 200
    assert response.get_json()["newPath"] == _relative(song, music_root)
    assert song.exists()


def test_smart_rename_file_adds_a_collision_suffix(
    client, auth_headers, audio_file, test_dir, music_root
):
    song = audio_file(".mp3", name="other.mp3")
    assert update_file_metadata(str(song), "title", "Taken")
    (test_dir / "Taken.mp3").write_bytes(b"existing")

    response = _smart_rename(client, auth_headers, song, music_root)

    assert response.status_code == 200
    assert response.get_json()["newName"] == "Taken (1).mp3"
    assert (test_dir / "Taken.mp3").read_bytes() == b"existing"


@pytest.mark.parametrize(
    "body,message",
    [
        ({"isFolder": "yes"}, "isFolder must be a boolean"),
        ({"replaceSpaces": 1}, "replaceSpaces must be a boolean"),
    ],
)
def test_smart_rename_validates_boolean_options(
    client, auth_headers, audio_file, music_root, body, message
):
    song = audio_file(".mp3", name="song.mp3")

    response = _smart_rename(client, auth_headers, song, music_root, **body)

    assert response.status_code == 400
    assert response.get_json()["error"] == message


def test_smart_rename_rejects_an_unsupported_file(
    client, auth_headers, test_dir, music_root
):
    notes = test_dir / "notes.txt"
    notes.write_bytes(b"text")

    response = _smart_rename(client, auth_headers, notes, music_root)

    assert response.status_code == 400
    assert "supported audio" in response.get_json()["error"]


def test_smart_rename_rejects_corrupt_audio(
    client, auth_headers, test_dir, music_root
):
    corrupt = test_dir / "corrupt.mp3"
    corrupt.write_bytes(b"not real audio")

    response = _smart_rename(client, auth_headers, corrupt, music_root)

    assert response.status_code == 400
    assert response.get_json()["error"] == (
        "Could not read metadata from the audio file"
    )


def test_smart_rename_missing_file_is_404(
    client, auth_headers, music_root
):
    response = _smart_rename(
        client, auth_headers, music_root / "missing.mp3", music_root
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "File not found"


def test_smart_rename_folder_without_audio_is_400(
    client, auth_headers, test_dir, music_root
):
    empty = test_dir / "empty"
    empty.mkdir()

    response = _post(
        client,
        auth_headers,
        "/api/apply-renaming-scheme",
        path=_relative(empty, music_root),
        scheme="[TITLE]",
        isFolder=True,
        replaceSpaces=False,
    )

    assert response.status_code == 400
    assert "No audio files" in response.get_json()["error"]


def test_file_operations_require_their_arguments(client, auth_headers):
    """Each operation must reject a request that omits a required path."""
    cases = [
        ("/api/delete", {}),
        ("/api/move", {"source": "song.mp3"}),
        ("/api/copy", {}),
    ]

    for route, body in cases:
        response = _post(client, auth_headers, route, **body)
        assert response.status_code == 400, route
        assert response.get_json()["error"], route


def test_copy_missing_path_is_404(client, auth_headers, music_root):
    response = _post(
        client, auth_headers, "/api/copy", path="does-not-exist.mp3"
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Path not found"


def test_delete_permission_error_is_403(
    client, auth_headers, test_dir, music_root, files_module, monkeypatch
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    def denied(path):
        raise PermissionError(path)

    monkeypatch.setattr(files_module.os, "remove", denied)

    response = _post(
        client, auth_headers, "/api/delete", path=_relative(song, music_root)
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == (
        "Permission denied while accessing the library."
    )
    assert song.read_bytes() == b"audio"


def test_delete_filesystem_error_is_500_and_keeps_the_file(
    client, auth_headers, test_dir, music_root, files_module, monkeypatch
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    def broken(path):
        raise OSError("I/O error")

    monkeypatch.setattr(files_module.os, "remove", broken)

    response = _post(
        client, auth_headers, "/api/delete", path=_relative(song, music_root)
    )

    assert response.status_code == 500
    assert song.read_bytes() == b"audio"


def test_move_permission_error_is_403(
    client, auth_headers, test_dir, music_root, files_module, monkeypatch
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    destination = test_dir / "destination"
    destination.mkdir()

    def denied(source, target):
        raise PermissionError(target)

    monkeypatch.setattr(files_module.shutil, "move", denied)

    response = _post(
        client,
        auth_headers,
        "/api/move",
        source=_relative(song, music_root),
        destination=_relative(destination, music_root),
    )

    assert response.status_code == 403
    assert song.is_file()
    assert not (destination / "song.mp3").exists()


def test_copy_permission_error_is_403(
    client, auth_headers, test_dir, music_root, files_module, monkeypatch
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    def denied(source, target):
        raise PermissionError(target)

    monkeypatch.setattr(files_module.shutil, "copy2", denied)

    response = _post(
        client, auth_headers, "/api/copy", path=_relative(song, music_root)
    )

    assert response.status_code == 403
    assert not (test_dir / "song - Copy.mp3").exists()


def test_rename_permission_error_is_403(
    client, auth_headers, test_dir, music_root, files_module, monkeypatch
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    def denied(source, target):
        raise PermissionError(target)

    monkeypatch.setattr(files_module.os, "rename", denied)

    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath=_relative(song, music_root),
        newName="renamed.mp3",
    )

    assert response.status_code == 403
    assert song.is_file()
    assert not (test_dir / "renamed.mp3").exists()


def test_smart_rename_missing_folder_is_404(
    client, auth_headers, test_dir, music_root
):
    response = _smart_rename(
        client,
        auth_headers,
        test_dir / "missing-album",
        music_root,
        isFolder=True,
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Folder not found"


def test_smart_rename_folder_requires_the_metadata_in_the_scheme(
    client, auth_headers, audio_file, test_dir, music_root
):
    audio_file(".mp3", name="album/song.mp3")

    response = _smart_rename(
        client,
        auth_headers,
        test_dir / "album",
        music_root,
        isFolder=True,
    )

    assert response.status_code == 400
    assert "Missing metadata fields" in response.get_json()["error"]
    assert (test_dir / "album").is_dir()


def test_smart_rename_file_requires_the_metadata_in_the_scheme(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")

    response = _smart_rename(client, auth_headers, song, music_root)

    assert response.status_code == 400
    assert "Missing metadata fields" in response.get_json()["error"]
    assert song.is_file()


def test_smart_rename_permission_error_is_403(
    client, auth_headers, audio_file, test_dir, music_root, files_module, monkeypatch
):
    song = audio_file(".mp3", name="song.mp3")
    assert update_file_metadata(str(song), "title", "Renamed")

    def denied(source, target):
        raise PermissionError(target)

    monkeypatch.setattr(files_module.os, "rename", denied)

    response = _smart_rename(client, auth_headers, song, music_root)

    assert response.status_code == 403
    assert song.is_file()
    assert not (test_dir / "Renamed.mp3").exists()


def test_smart_rename_reports_an_unexpected_error(
    client, auth_headers, audio_file, music_root, files_module, monkeypatch
):
    song = audio_file(".mp3", name="song.mp3")

    def broken(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(files_module, "generate_name_from_scheme", broken)

    response = _smart_rename(client, auth_headers, song, music_root)

    assert response.status_code == 500
    assert response.get_json()["error"] == "Smart rename failed."


def test_rename_refuses_a_destination_that_cannot_be_compared(
    client, auth_headers, test_dir, music_root, files_module, monkeypatch
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"source")
    existing = test_dir / "existing.mp3"
    existing.write_bytes(b"existing")

    def broken(first, second):
        raise OSError("cannot compare")

    monkeypatch.setattr(files_module.os.path, "samefile", broken)

    response = _post(
        client,
        auth_headers,
        "/api/rename",
        oldPath=_relative(song, music_root),
        newName="existing.mp3",
    )

    assert response.status_code == 409
    assert song.read_bytes() == b"source"
    assert existing.read_bytes() == b"existing"


@pytest.mark.parametrize("is_folder", [True, False])
def test_smart_rename_rejects_an_empty_generated_name(
    client,
    auth_headers,
    test_dir,
    music_root,
    files_module,
    monkeypatch,
    is_folder,
):
    album = test_dir / "album"
    album.mkdir()
    song = album / "song.mp3"
    song.write_bytes(b"audio")
    monkeypatch.setattr(
        files_module, "extract_metadata", lambda *a, **k: {"title": "<>"}
    )

    response = _post(
        client,
        auth_headers,
        "/api/apply-renaming-scheme",
        path=_relative(album if is_folder else song, music_root),
        scheme="[TITLE]",
        isFolder=is_folder,
        replaceSpaces=False,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Generated name is empty"
    assert album.is_dir()
    assert song.is_file()
