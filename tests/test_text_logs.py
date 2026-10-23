"""Text-file and log endpoint edge cases (B-19, B-20, B-21, B-27)."""

import errno
from pathlib import Path


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def test_text_save_rejects_non_string_content(
    client, auth_headers, test_dir, music_root
):
    lyrics = test_dir / "song.lrc"
    lyrics.write_bytes(b"original")

    response = client.post(
        "/api/text/save",
        headers=auth_headers,
        json={"path": _relative(lyrics, music_root), "content": ["not", "text"]},
    )

    assert response.status_code == 400
    assert lyrics.read_bytes() == b"original"


def test_failed_text_write_preserves_the_original(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    lyrics = test_dir / "song.lrc"
    lyrics.write_bytes(b"original")

    def fail_replace(source, destination):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(app_module.os, "replace", fail_replace)

    response = client.post(
        "/api/text/save",
        headers=auth_headers,
        json={"path": _relative(lyrics, music_root), "content": "new"},
    )

    assert response.status_code == 500
    assert lyrics.read_bytes() == b"original"
    assert not list(test_dir.glob(".upload-*.part"))


def test_text_save_rejects_oversized_content(
    client, auth_headers, test_dir, music_root, app_module
):
    lyrics = test_dir / "song.lrc"
    lyrics.write_bytes(b"original")
    content = "x" * (app_module.TEXT_MAX_BYTES + 1)

    response = client.post(
        "/api/text/save",
        headers=auth_headers,
        json={"path": _relative(lyrics, music_root), "content": content},
    )

    assert response.status_code == 413
    assert lyrics.read_bytes() == b"original"


def test_text_read_replaces_invalid_utf8(client, auth_headers, test_dir, music_root):
    lyrics = test_dir / "song.lrc"
    lyrics.write_bytes(b"caf\xe9")

    response = client.get(
        "/api/text",
        headers=auth_headers,
        query_string={"path": _relative(lyrics, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()["content"] == "caf\ufffd"


def test_text_read_rejects_oversized_files(
    client, auth_headers, test_dir, music_root, app_module
):
    lyrics = test_dir / "song.lrc"
    lyrics.write_bytes(b"x" * (app_module.TEXT_MAX_BYTES + 1))

    response = client.get(
        "/api/text",
        headers=auth_headers,
        query_string={"path": _relative(lyrics, music_root)},
    )

    assert response.status_code == 413
    assert response.is_json


def test_log_line_count_is_clamped(
    client, auth_headers, app_module, tmp_path, monkeypatch
):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(app_module, "LOG_DIR", logs)
    log_file = logs / "app.log"
    log_file.write_text(
        "".join(
            f"[2024-01-01 00:00:0{i}] [INFO] line {i}\n" for i in range(5)
        )
    )

    for requested, expected in ((0, 1), (-1, 1), (99999, 5)):
        response = client.get(
            f"/api/logs?lines={requested}",
            headers=auth_headers,
        )

        assert response.status_code == 200, requested
        assert response.get_json()["displayed"] == expected
