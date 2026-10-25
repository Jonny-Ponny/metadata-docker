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


def test_text_read_returns_the_file_content(
    client, auth_headers, test_dir, music_root
):
    lyrics = test_dir / "song.lrc"
    lyrics.write_text("[00:01.00] First line\n", encoding="utf-8")

    response = client.get(
        "/api/text",
        headers=auth_headers,
        query_string={"path": _relative(lyrics, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json() == {"content": "[00:01.00] First line\n"}


def test_text_read_requires_a_path(client, auth_headers):
    response = client.get("/api/text", headers=auth_headers)

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing path parameter"


def test_text_read_missing_file_is_404(client, auth_headers, music_root):
    response = client.get(
        "/api/text",
        headers=auth_headers,
        query_string={"path": "missing.lrc"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "File not found"


def test_text_read_rejects_a_non_text_file(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = client.get(
        "/api/text",
        headers=auth_headers,
        query_string={"path": _relative(song, music_root)},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Not a text file"


def test_text_save_requires_path_and_content(client, auth_headers):
    for body in ({}, {"path": "song.lrc"}, {"content": "text"}):
        response = client.post(
            "/api/text/save", headers=auth_headers, json=body
        )
        assert response.status_code == 400
        assert response.get_json()["error"] == "Missing path or content"


def test_log_line_count_is_clamped(
    client, auth_headers, logs_module, tmp_path, monkeypatch
):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(logs_module, "LOG_DIR", logs)
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


def _log_dir(tmp_path, monkeypatch, logs_module, content=None):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(logs_module, "LOG_DIR", logs)
    if content is not None:
        (logs / "app.log").write_text(content, encoding="utf-8")
    return logs


def test_logs_missing_file_is_an_empty_result(
    client, auth_headers, logs_module, tmp_path, monkeypatch
):
    _log_dir(tmp_path, monkeypatch, logs_module)

    response = client.get("/api/logs", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {
        "logs": [],
        "total": 0,
        "message": "No logs found",
    }


def test_logs_filter_by_level_and_search(
    client, auth_headers, logs_module, tmp_path, monkeypatch
):
    _log_dir(
        tmp_path,
        monkeypatch,
        logs_module,
        "[2024-01-01 10:00:00] [INFO] Started\n"
        "[2024-01-01 10:00:01] [ERROR] Upload failed\n"
        "[2024-01-01 10:00:02] [INFO] Upload retried\n",
    )

    response = client.get("/api/logs?level=error", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert [entry["message"] for entry in body["logs"]] == ["Upload failed"]
    assert body["filters"] == {"level": "error", "search": None}

    response = client.get("/api/logs?search=upload", headers=auth_headers)
    body = response.get_json()
    assert [entry["message"] for entry in body["logs"]] == [
        "Upload failed",
        "Upload retried",
    ]

    response = client.get(
        "/api/logs?level=info&search=retried", headers=auth_headers
    )
    body = response.get_json()
    assert [entry["message"] for entry in body["logs"]] == ["Upload retried"]


def test_logs_keep_unparseable_lines_as_raw(
    client, auth_headers, logs_module, tmp_path, monkeypatch
):
    _log_dir(
        tmp_path,
        monkeypatch,
        logs_module,
        "[2024-01-01 10:00:00] [INFO] Started\n"
        "a line without the log prefix\n",
    )

    response = client.get("/api/logs", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["logs"] == [
        {"timestamp": "2024-01-01 10:00:00", "level": "INFO", "message": "Started"},
        {"raw": "a line without the log prefix"},
    ]


def test_logs_clear_empties_the_file(
    client, auth_headers, logs_module, tmp_path, monkeypatch
):
    logs = _log_dir(
        tmp_path,
        monkeypatch,
        logs_module,
        "[2024-01-01 10:00:00] [INFO] Started\n",
    )

    response = client.post("/api/logs/clear", headers=auth_headers)

    assert response.status_code == 200
    assert (logs / "app.log").read_text() == ""

    response = client.get("/api/logs", headers=auth_headers)
    assert response.get_json()["logs"] == []
    assert response.get_json()["total"] == 0


def test_logs_clear_without_a_log_file_succeeds(
    client, auth_headers, logs_module, tmp_path, monkeypatch
):
    logs = _log_dir(tmp_path, monkeypatch, logs_module)

    response = client.post("/api/logs/clear", headers=auth_headers)

    assert response.status_code == 200
    assert not (logs / "app.log").exists()
