"""Upload and folder-creation behaviour.

These complement the security suite: the upload flow is where a stale client
used to create duplicate folders and files, so the conflict policies and the
atomic write are covered here.
"""

import errno
import io
from pathlib import Path

import pytest


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _upload(
    client,
    auth_headers,
    *,
    content=b"audio",
    filename="song.mp3",
    target="",
    conflict=None,
):
    data = {
        "file": (io.BytesIO(content), filename),
        "targetPath": target,
        "originalFilename": filename,
    }
    if conflict is not None:
        data["conflict"] = conflict
    return client.post("/api/upload", headers=auth_headers, data=data)


def test_skip_identical_leaves_the_existing_file_untouched(
    client, auth_headers, test_dir, music_root
):
    existing = test_dir / "song.mp3"
    existing.write_bytes(b"AAAAA")

    response = _upload(client, auth_headers, content=b"BBBBB", target=_relative(test_dir, music_root))

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["skipped"] is True
    assert existing.read_bytes() == b"AAAAA"
    assert not (test_dir / "song (1).mp3").exists()


def test_different_size_is_renamed_under_the_skip_policy(
    client, auth_headers, test_dir, music_root
):
    existing = test_dir / "song.mp3"
    existing.write_bytes(b"short")

    response = _upload(
        client,
        auth_headers,
        content=b"a much longer payload",
        target=_relative(test_dir, music_root),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["skipped"] is False
    assert body["renamed"] is True
    assert existing.read_bytes() == b"short"
    assert (test_dir / "song (1).mp3").read_bytes() == b"a much longer payload"


def test_keep_both_always_renames(client, auth_headers, test_dir, music_root):
    existing = test_dir / "song.mp3"
    existing.write_bytes(b"AAAAA")

    response = _upload(
        client,
        auth_headers,
        content=b"BBBBB",
        target=_relative(test_dir, music_root),
        conflict="keep-both",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["skipped"] is False
    assert body["renamed"] is True
    assert existing.read_bytes() == b"AAAAA"
    assert (test_dir / "song (1).mp3").read_bytes() == b"BBBBB"


def test_upload_rejects_a_directory_name_collision(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "album").mkdir()

    response = _upload(
        client,
        auth_headers,
        filename="album",
        target=_relative(test_dir, music_root),
    )

    assert response.status_code == 400
    assert "folder" in response.get_json()["error"].lower()


def test_invalid_upload_conflict_policy_is_rejected(
    client, auth_headers, test_dir, music_root
):
    response = _upload(
        client,
        auth_headers,
        target=_relative(test_dir, music_root),
        conflict="replace",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid conflict policy"


def test_mkdir_merge_returns_the_existing_folder(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "Album"
    album.mkdir()
    relative = _relative(album, music_root)

    response = client.post(
        "/api/mkdir",
        headers=auth_headers,
        json={"path": relative, "conflict": "merge"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["created"] is False
    assert body["path"] == relative
    assert album.is_dir()
    assert not (test_dir / "Album (1)").exists()


def test_mkdir_merge_is_idempotent_when_the_folder_appears_concurrently(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    """Two workers uploading the same new folder must not produce a 409.

    The old route checked whether the folder existed and then called
    ``os.makedirs(exist_ok=False)``, so a second worker that saw no folder
    failed with ``FileExistsError``. Simulate the concurrent creation inside
    the call: the merge must still succeed instead of answering 409.
    """
    album = test_dir / "Album"
    real_makedirs = app_module.os.makedirs
    calls = []

    def racing_makedirs(path, mode=0o777, exist_ok=False):
        calls.append(exist_ok)
        # The other upload worker creates the folder first.
        album.mkdir(exist_ok=True)
        return real_makedirs(path, mode=mode, exist_ok=exist_ok)

    monkeypatch.setattr(app_module.os, "makedirs", racing_makedirs)

    response = client.post(
        "/api/mkdir",
        headers=auth_headers,
        json={"path": _relative(album, music_root), "conflict": "merge"},
    )

    assert response.status_code == 200
    assert calls == [True]
    body = response.get_json()
    assert body["path"] == _relative(album, music_root)
    assert album.is_dir()
    assert not (test_dir / "Album (1)").exists()


def test_mkdir_rename_retries_when_the_name_is_taken_concurrently(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    target = test_dir / "Album"
    real_makedirs = app_module.os.makedirs

    def racing_makedirs(path, mode=0o777, exist_ok=False):
        target.mkdir(exist_ok=True)
        return real_makedirs(path, mode=mode, exist_ok=exist_ok)

    monkeypatch.setattr(app_module.os, "makedirs", racing_makedirs)

    response = client.post(
        "/api/mkdir",
        headers=auth_headers,
        json={"path": _relative(target, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()["path"].endswith("Album (1)")
    assert (test_dir / "Album (1)").is_dir()


def test_mkdir_merge_rejects_a_file_with_the_same_name(
    client, auth_headers, test_dir, music_root
):
    (test_dir / "Album").write_bytes(b"not a folder")

    response = client.post(
        "/api/mkdir",
        headers=auth_headers,
        json={"path": _relative(test_dir / "Album", music_root), "conflict": "merge"},
    )

    assert response.status_code == 400
    assert "file" in response.get_json()["error"].lower()


def test_mkdir_default_still_renames(client, auth_headers, test_dir, music_root):
    album = test_dir / "Album"
    album.mkdir()

    response = client.post(
        "/api/mkdir",
        headers=auth_headers,
        json={"path": _relative(album, music_root)},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["created"] is True
    assert body["path"].endswith("Album (1)")
    assert (test_dir / "Album (1)").is_dir()


def test_invalid_mkdir_conflict_policy_is_rejected(
    client, auth_headers, test_dir, music_root
):
    response = client.post(
        "/api/mkdir",
        headers=auth_headers,
        json={"path": _relative(test_dir / "New", music_root), "conflict": "merge?"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid conflict policy"


def test_storage_endpoint_requires_auth_and_reports_space(client, auth_headers):
    assert client.get("/api/storage").status_code == 401

    response = client.get("/api/storage", headers=auth_headers)
    assert response.status_code == 200

    body = response.get_json()
    assert body["music"]["free"] >= 0
    assert body["music"]["total"] >= body["music"]["free"]
    assert body["temp"]["free"] >= 0
    assert body["headroom"] >= 0


def test_version_reports_the_upload_limit(client, app_module):
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.get_json()["max_upload_bytes"] == app_module.MAX_UPLOAD_BYTES


def test_failed_write_leaves_no_partial_file(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    def fail_replace(source, destination):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(app_module.os, "replace", fail_replace)

    response = _upload(
        client,
        auth_headers,
        content=b"x" * 1024,
        target=_relative(test_dir, music_root),
    )

    assert response.status_code == 500
    assert "disk space" in response.get_json()["error"].lower()
    # Neither the destination nor the hidden temp file may survive.
    assert list(test_dir.iterdir()) == []


def test_upload_creates_the_target_folder(
    client, auth_headers, test_dir, music_root
):
    target = f"{_relative(test_dir, music_root)}/Nested/Album"

    response = _upload(
        client,
        auth_headers,
        content=b"audio",
        target=target,
        filename="track.mp3",
    )

    assert response.status_code == 200
    assert (test_dir / "Nested" / "Album" / "track.mp3").read_bytes() == b"audio"


@pytest.mark.parametrize("target", ["../outside", "Nested/../../outside"])
def test_upload_cannot_escape_the_library(
    client, auth_headers, target, music_root
):
    response = _upload(client, auth_headers, target=target)

    assert response.status_code == 403
    assert not (music_root.parent / "outside").exists()
