"""Upload and folder-creation behaviour, including the upload race (B-07).

These complement the security suite: the upload flow is where a stale client
used to create duplicate folders and files, so the conflict policies and the
atomic write are covered here.
"""

import errno
import io
from pathlib import Path

import pytest

from config import STORAGE_HEADROOM_BYTES


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
    assert body["temp"]["total"] >= body["temp"]["free"]
    assert body["headroom"] == STORAGE_HEADROOM_BYTES


def test_version_reports_the_upload_limit(client, app_module):
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.get_json()["max_upload_bytes"] == app_module.MAX_UPLOAD_BYTES


def test_failed_write_leaves_no_partial_file(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    def fail_link(source, destination):
        raise OSError(errno.ENOSPC, "No space left on device")

    # The upload claims its destination with os.link() so it cannot overwrite
    # a file another upload just created.
    monkeypatch.setattr(app_module.os, "link", fail_link)

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


def test_concurrent_upload_keeps_both_files(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    """Two workers uploading the same name must not overwrite each other.

    ``_unique_path()`` used to check and return a name, so both workers could
    pick "song.mp3" and the second ``os.replace()`` clobbered the first. The
    race is simulated by having "the other worker" create the file between the
    existence check and the atomic claim.
    """
    real_link = app_module.os.link
    other = test_dir / "song.mp3"
    raced = []

    def racing_link(source, destination):
        if not raced:
            raced.append(True)
            other.write_bytes(b"other payload")
        return real_link(source, destination)

    monkeypatch.setattr(app_module.os, "link", racing_link)

    response = _upload(
        client,
        auth_headers,
        content=b"second payload",
        target=_relative(test_dir, music_root),
        conflict="keep-both",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["skipped"] is False
    assert body["renamed"] is True
    assert body["filename"] == "song (1).mp3"
    assert other.read_bytes() == b"other payload"
    assert (test_dir / "song (1).mp3").read_bytes() == b"second payload"


def test_concurrent_identical_upload_is_skipped(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    real_link = app_module.os.link
    other = test_dir / "song.mp3"
    raced = []

    def racing_link(source, destination):
        if not raced:
            raced.append(True)
            other.write_bytes(b"other payload")
        return real_link(source, destination)

    monkeypatch.setattr(app_module.os, "link", racing_link)

    response = _upload(
        client,
        auth_headers,
        content=b"first payload",
        target=_relative(test_dir, music_root),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["skipped"] is True
    assert body["filename"] == "song.mp3"
    assert other.read_bytes() == b"other payload"
    assert not (test_dir / "song (1).mp3").exists()


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


def test_invalid_filename_does_not_create_the_target_folder(
    client, auth_headers, test_dir, music_root
):
    """B-28: validate the name before ``os.makedirs()``."""
    target = f"{_relative(test_dir, music_root)}/Nested/Album"

    response = _upload(client, auth_headers, filename="..", target=target)

    assert response.status_code == 400
    assert not (test_dir / "Nested").exists()


def test_upload_without_a_file_part_is_rejected(client, auth_headers):
    response = client.post(
        "/api/upload", headers=auth_headers, data={"targetPath": ""}
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "No file part"


def test_upload_with_an_empty_filename_is_rejected(client, auth_headers):
    response = _upload(client, auth_headers, content=b"", filename="")

    assert response.status_code == 400
    assert response.get_json()["error"] == "No selected file"


def test_upload_target_must_be_a_folder(
    client, auth_headers, test_dir, music_root
):
    target = test_dir / "already-a-file"
    target.write_bytes(b"not a folder")

    response = _upload(
        client,
        auth_headers,
        target=_relative(target, music_root),
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Upload target is not a folder"


def test_original_filename_backslashes_cannot_change_the_folder(
    client, auth_headers, test_dir, music_root
):
    response = client.post(
        "/api/upload",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"audio"), "ignored.mp3"),
            "targetPath": _relative(test_dir, music_root),
            "originalFilename": "nested\\track.mp3",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["filename"] == "track.mp3"
    assert body["original_filename"] == "nested\\track.mp3"
    assert (test_dir / "track.mp3").read_bytes() == b"audio"
    assert not (test_dir / "nested").exists()


def test_original_filename_nul_bytes_are_removed(
    client, auth_headers, test_dir, music_root
):
    response = client.post(
        "/api/upload",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"audio"), "ignored.mp3"),
            "targetPath": _relative(test_dir, music_root),
            "originalFilename": "bad\0name.mp3",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["filename"] == "badname.mp3"
    assert (test_dir / "badname.mp3").is_file()


def test_upload_falls_back_when_the_filename_is_missing(
    client, auth_headers, test_dir, music_root
):
    response = client.post(
        "/api/upload",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"audio"), "from-part.mp3"),
            "targetPath": _relative(test_dir, music_root),
        },
    )

    assert response.status_code == 200
    assert (test_dir / "from-part.mp3").is_file()


def test_claim_upload_falls_back_to_exclusive_create(tmp_path, monkeypatch):
    import routes.files as files

    def no_hardlinks(source, destination):
        raise OSError(errno.EPERM, "hard links are not supported")

    monkeypatch.setattr(files.os, "link", no_hardlinks)
    temp = tmp_path / "temp.part"
    temp.write_bytes(b"payload")
    destination = tmp_path / "song.mp3"

    assert files._claim_upload(str(temp), str(destination)) is True
    assert destination.read_bytes() == b"payload"
    assert not temp.exists()


def test_claim_upload_fallback_does_not_replace_an_existing_file(
    tmp_path, monkeypatch
):
    import routes.files as files

    def no_hardlinks(source, destination):
        raise OSError(errno.EOPNOTSUPP, "hard links are not supported")

    monkeypatch.setattr(files.os, "link", no_hardlinks)
    temp = tmp_path / "temp.part"
    temp.write_bytes(b"payload")
    destination = tmp_path / "song.mp3"
    destination.write_bytes(b"existing")

    assert files._claim_upload(str(temp), str(destination)) is False
    assert destination.read_bytes() == b"existing"


def test_claim_upload_removes_the_claim_when_rename_fails(
    tmp_path, monkeypatch
):
    import routes.files as files

    def no_hardlinks(source, destination):
        raise OSError(errno.EPERM, "hard links are not supported")

    def fail_replace(source, destination):
        raise OSError(errno.ENOSPC, "disk is full")

    monkeypatch.setattr(files.os, "link", no_hardlinks)
    monkeypatch.setattr(files.os, "replace", fail_replace)
    temp = tmp_path / "temp.part"
    temp.write_bytes(b"payload")
    destination = tmp_path / "song.mp3"

    with pytest.raises(OSError):
        files._claim_upload(str(temp), str(destination))

    assert not destination.exists()
    assert temp.exists()


def test_claim_upload_propagates_unexpected_link_errors(tmp_path, monkeypatch):
    import routes.files as files

    def fail_link(source, destination):
        raise OSError(errno.ENOSPC, "disk is full")

    monkeypatch.setattr(files.os, "link", fail_link)
    temp = tmp_path / "temp.part"
    temp.write_bytes(b"payload")

    with pytest.raises(OSError):
        files._claim_upload(str(temp), str(tmp_path / "song.mp3"))


def test_same_size_handles_missing_values_and_errors(tmp_path, monkeypatch):
    import routes.files as files

    song = tmp_path / "song.mp3"
    song.write_bytes(b"1234")

    assert files._same_size(str(song), None) is False
    assert files._same_size(str(tmp_path / "missing"), 4) is False
    assert files._same_size(str(song), 4) is True

    def fail_getsize(path):
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr(files.os.path, "getsize", fail_getsize)
    assert files._same_size(str(song), 4) is False


def test_stream_size_returns_none_for_unreadable_streams():
    import routes.files as files

    class BadStream:
        def tell(self):
            raise OSError("not seekable")

    class Storage:
        stream = BadStream()

    assert files._stream_size(Storage()) is None
    assert files._stream_size(object()) is None


def test_save_upload_removes_the_temp_file_when_saving_fails(tmp_path):
    import routes.files as files

    class FailingStorage:
        stream = None

        def save(self, path):
            Path(path).write_bytes(b"partial")
            raise OSError(errno.ENOSPC, "disk is full")

    with pytest.raises(OSError):
        files._save_upload_atomic(
            FailingStorage(), str(tmp_path), "song.mp3", "keep-both"
        )

    assert list(tmp_path.iterdir()) == []
