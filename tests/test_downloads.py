"""File and folder downloads, download tokens and ZIP streaming."""

import datetime
import io
from pathlib import Path
from urllib.parse import quote, unquote
import zipfile

import jwt
import pytest


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _zip_names(response):
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        return archive.namelist()


def test_file_download_headers_and_body(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio-data")

    response = client.post(
        "/api/download",
        headers=auth_headers,
        json={"path": _relative(song, music_root), "isFolder": False},
    )

    assert response.status_code == 200
    assert response.data == b"audio-data"
    assert response.mimetype == "audio/mpeg"
    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="song.mp3"' in disposition
    assert "filename*=UTF-8''song.mp3" in disposition


def test_download_header_survives_a_unicode_filename(
    client, auth_headers, test_dir, music_root
):
    name = "café ☕.mp3"
    song = test_dir / name
    song.write_bytes(b"audio")

    response = client.post(
        "/api/download",
        headers=auth_headers,
        json={"path": _relative(song, music_root), "isFolder": False},
    )

    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == name
    # The fallback name is pure ASCII and uses placeholders for non-ASCII.
    fallback = disposition.split('filename="', 1)[1].split('"', 1)[0]
    assert fallback.isascii()
    assert fallback.endswith(".mp3")
    assert encoded == quote(name, safe="")


def test_folder_download_contains_nested_files(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "album"
    (album / "cd1").mkdir(parents=True)
    (album / "song.mp3").write_bytes(b"one")
    (album / "cd1" / "track.flac").write_bytes(b"two")

    response = client.post(
        "/api/download",
        headers=auth_headers,
        json={"path": _relative(album, music_root), "isFolder": True},
    )

    assert response.mimetype == "application/zip"
    assert response.headers["X-Accel-Buffering"] == "no"
    disposition = response.headers["Content-Disposition"]
    assert "album.zip" in disposition
    assert sorted(_zip_names(response)) == [
        "album/cd1/track.flac",
        "album/song.mp3",
    ]


def test_folder_download_skips_symlinks_that_leave_the_folder(
    client, auth_headers, test_dir, music_root, tmp_path
):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "nested.mp3").write_bytes(b"nested")

    album = test_dir / "album"
    album.mkdir()
    (album / "song.mp3").write_bytes(b"audio")
    (album / "outside-link.mp3").symlink_to(outside)
    (album / "outside-dir-link").symlink_to(outside_dir)
    (album / "inside-link.mp3").symlink_to(album / "song.mp3")

    response = client.post(
        "/api/download",
        headers=auth_headers,
        json={"path": _relative(album, music_root), "isFolder": True},
    )

    names = _zip_names(response)
    assert "album/song.mp3" in names
    # An inside-pointing link is still part of the folder.
    assert "album/inside-link.mp3" in names
    assert "album/outside-link.mp3" not in names
    assert not any(name.startswith("album/outside-dir-link") for name in names)


def test_empty_folder_download_is_a_valid_empty_zip(
    client, auth_headers, test_dir, music_root
):
    empty = test_dir / "empty"
    empty.mkdir()

    response = client.post(
        "/api/download",
        headers=auth_headers,
        json={"path": _relative(empty, music_root), "isFolder": True},
    )

    assert _zip_names(response) == []


def test_iter_zip_raises_before_the_first_byte(test_dir, monkeypatch):
    import zip_stream

    def fail(folder_path, destination):
        raise RuntimeError("cannot read the folder")

    monkeypatch.setattr(zip_stream, "_write_archive", fail)

    with pytest.raises(RuntimeError, match="cannot read the folder"):
        list(zip_stream.iter_zip(str(test_dir)))


def test_iter_zip_raises_after_data_was_sent(test_dir, monkeypatch):
    import zip_stream

    def write_then_fail(folder_path, destination):
        destination.write(b"x" * 64)
        raise RuntimeError("failed halfway")

    monkeypatch.setattr(zip_stream, "_write_archive", write_then_fail)

    chunks = zip_stream.iter_zip(str(test_dir), chunk_size=16)

    assert next(chunks) == b"x" * 64
    with pytest.raises(RuntimeError, match="failed halfway"):
        next(chunks)


def _download_token(client, auth_headers, path, is_folder=False):
    response = client.post(
        "/api/download-token",
        headers=auth_headers,
        json={"path": path, "isFolder": is_folder},
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def _signed_download_token(app_module, **overrides):
    payload = {
        "username": app_module.AUTH_USERNAME,
        "scope": app_module.TOKEN_SCOPE_DOWNLOAD,
        "path": "song.mp3",
        "isFolder": False,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=2),
    }
    payload.update(overrides)
    return jwt.encode(
        payload,
        app_module.app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def test_download_token_works_for_the_issued_file(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    token = _download_token(client, auth_headers, _relative(song, music_root))

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 200
    assert response.data == b"audio"


def test_expired_download_token_is_rejected(client, app_module):
    token = _signed_download_token(
        app_module,
        exp=datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(seconds=1),
    )

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Download link has expired"


def test_tampered_download_token_is_rejected(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    token = _download_token(client, auth_headers, _relative(song, music_root))
    header, payload, signature = token.split(".")
    tampered = ".".join(
        (header, payload, signature[:-1] + ("A" if signature[-1] != "A" else "B"))
    )

    response = client.get("/api/download", query_string={"token": tampered})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_download_token_cannot_escape_the_library(client, app_module, tmp_path):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")
    token = _signed_download_token(app_module, path="../outside.mp3")

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 403
    assert response.is_json
    assert outside.read_bytes() == b"secret"


def test_download_token_for_another_user_is_rejected(client, app_module):
    token = _signed_download_token(app_module, username="someone-else")

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_missing_download_path_is_a_json_400(client, auth_headers):
    response = client.post("/api/download", headers=auth_headers, json={})

    assert response.status_code == 400
    assert response.is_json


def test_download_requires_a_token(client):
    response = client.get("/api/download")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is missing"


def test_a_token_without_a_download_scope_is_rejected(client, app_module):
    token = _signed_download_token(app_module, scope="session")

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_a_download_token_without_a_path_is_rejected(client, app_module):
    token = _signed_download_token(app_module, path="")

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_a_token_for_a_deleted_target_is_404(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    token = _download_token(client, auth_headers, _relative(song, music_root))
    song.unlink()

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 404
    assert response.get_json()["error"] == "Path not found"


def test_a_file_token_marked_as_a_folder_cannot_download(
    client, auth_headers, test_dir, music_root
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")
    token = _download_token(
        client, auth_headers, _relative(song, music_root), is_folder=True
    )

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid item type"


def test_content_disposition_sanitises_quotes_backslashes_and_newlines():
    from routes import downloads

    header = downloads._content_disposition('a"b\\c\r\nd \u00e9.mp3')

    assert header.startswith('attachment; filename="a_b_c__d _.mp3"; ')
    assert "filename*=UTF-8''" in header
    assert "\r" not in header
    assert "\n" not in header
