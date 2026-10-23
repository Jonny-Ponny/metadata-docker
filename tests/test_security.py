"""Security regression tests.
"""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def test_download_token_is_rejected_by_session_routes(
    client, auth_headers, music_root, test_dir
):
    audio = test_dir / "song.mp3"
    audio.write_bytes(b"audio-data")

    response = client.post(
        "/api/download-token",
        headers=auth_headers,
        json={"path": _relative(audio, music_root)},
    )
    assert response.status_code == 200
    download_token = response.get_json()["token"]

    response = client.get(
        "/api/validate",
        headers={"Authorization": f"Bearer {download_token}"},
    )
    assert response.status_code == 401

    # The same token must still work for the download route it was issued for.
    response = client.get(
        "/api/download",
        query_string={"token": download_token},
    )
    assert response.status_code == 200
    assert response.data == b"audio-data"


def test_unset_credentials_never_become_admin_admin(app_module, tmp_path):
    backend_dir = Path(app_module.__file__).resolve().parent
    music = tmp_path / "music"
    logs = tmp_path / "logs"
    work = tmp_path / "work"
    for directory in (music, logs, work):
        directory.mkdir()

    env = os.environ.copy()
    for key in ("AUTH_USERNAME", "AUTH_PASSWORD", "AUTH_PASSWORD_HASH"):
        env.pop(key, None)
    env.update(
        {
            "PYTHONPATH": str(backend_dir),
            "MUSIC_FOLDER": str(music),
            "LOG_DIR": str(logs),
            "DISABLE_VERSION_CHECK": "true",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    script = (
        "import json, app; "
        "print('CREDS=' + json.dumps([app.AUTH_USERNAME, app.AUTH_PASSWORD]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    marker = next(
        line for line in result.stdout.splitlines() if line.startswith("CREDS=")
    )
    username, password = json.loads(marker.split("=", 1)[1])

    assert username
    assert password
    assert (username, password) != ("admin", "admin")
    assert username != "admin"


def test_empty_music_folder_falls_back_to_the_default(app_module, tmp_path):
    """An empty MUSIC_FOLDER must not disable the path containment check (B-04).

    A missing default used to leave ``safe_path()`` returning the raw user
    path, so an absolute path could escape the library.
    """
    backend_dir = Path(app_module.__file__).resolve().parent
    logs = tmp_path / "logs"
    work = tmp_path / "work"
    for directory in (logs, work):
        directory.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(backend_dir),
            "MUSIC_FOLDER": "",
            "LOG_DIR": str(logs),
            "DISABLE_VERSION_CHECK": "true",
            "AUTH_USERNAME": "test-admin",
            "AUTH_PASSWORD": "test-password",
            "AUTH_PASSWORD_HASH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    script = (
        "import app\n"
        "print('ROOT=' + app.MUSIC_ROOT)\n"
        "path = app.safe_path('/etc/passwd')\n"
        "print('PATH=' + path)\n"
        "print('INSIDE=' + str(app._is_within(app.MUSIC_ROOT, path)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    output = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    assert output["ROOT"] == "/music"
    assert output["INSIDE"] == "True"


def test_safe_path_allows_symlinks_inside_the_library(
    app_module, music_root, test_dir
):
    target = test_dir / "song.mp3"
    target.write_bytes(b"audio")

    link = music_root / f"inside-{uuid.uuid4().hex}"
    link.symlink_to(target)

    resolved = app_module.safe_path(link.name)
    assert app_module._is_within(app_module.MUSIC_ROOT, resolved)
    assert Path(os.path.realpath(resolved)) == target.resolve()


def test_safe_path_rejects_symlink_escapes(app_module, music_root, tmp_path):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"secret")

    link = music_root / f"outside-{uuid.uuid4().hex}"
    link.symlink_to(outside)

    with pytest.raises(app_module.AccessDenied):
        app_module.safe_path(link.name)

    with pytest.raises(app_module.AccessDenied):
        app_module.safe_path("../outside.mp3")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.10/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[fd00::1]/",
    ],
)
def test_ssrf_blocks_non_public_addresses(url):
    from safe_fetch import UnsafeURLError, validate_public_url

    with pytest.raises(UnsafeURLError, match="non-public"):
        validate_public_url(url)


def test_ssrf_revalidates_redirect_targets(monkeypatch):
    import safe_fetch

    class RedirectResponse:
        status_code = 302
        headers = {"Location": "http://127.0.0.1/secret"}

        def close(self):
            pass

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return RedirectResponse()

    monkeypatch.setattr(safe_fetch.requests, "get", fake_get)

    with pytest.raises(safe_fetch.UnsafeURLError, match="non-public"):
        safe_fetch.fetch_image("http://1.1.1.1/start.jpg", "test-agent")

    assert calls == ["http://1.1.1.1/start.jpg"]


def test_smart_rename_rejects_dot_names(
    client, auth_headers, music_root, test_dir, app_module, monkeypatch
):
    album = test_dir / "album"
    album.mkdir()
    song = album / "song.mp3"
    song.write_bytes(b"audio")

    monkeypatch.setattr(
        app_module, "extract_metadata", lambda *args, **kwargs: {"title": ".."}
    )

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={
            "path": _relative(album, music_root),
            "scheme": "[TITLE]",
            "isFolder": True,
            "replaceSpaces": False,
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid generated name"
    assert album.is_dir()

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={
            "path": _relative(song, music_root),
            "scheme": "[TITLE]",
            "isFolder": False,
            "replaceSpaces": False,
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid generated name"
    assert song.is_file()


def test_smart_rename_cannot_rename_the_library_root(
    client, auth_headers, music_root, test_dir, app_module, monkeypatch
):
    (test_dir / "song.mp3").write_bytes(b"audio")
    generated = f"Escaped-{uuid.uuid4().hex}"

    monkeypatch.setattr(
        app_module,
        "extract_metadata",
        lambda *args, **kwargs: {"title": generated},
    )

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={
            "path": "/",
            "scheme": "[TITLE]",
            "isFolder": True,
            "replaceSpaces": False,
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid generated name"
    assert music_root.is_dir()
    assert not (music_root.parent / generated).exists()


def test_smart_rename_still_applies_safe_names(
    client, auth_headers, music_root, test_dir, app_module, monkeypatch
):
    album = test_dir / "album"
    album.mkdir()
    (album / "song.mp3").write_bytes(b"audio")
    generated = f"Renamed-{uuid.uuid4().hex}"

    monkeypatch.setattr(
        app_module,
        "extract_metadata",
        lambda *args, **kwargs: {"title": generated},
    )

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={
            "path": _relative(album, music_root),
            "scheme": "[TITLE]",
            "isFolder": True,
            "replaceSpaces": False,
        },
    )
    assert response.status_code == 200
    assert (test_dir / generated).is_dir()


def test_oversized_upload_returns_json_413(
    client, auth_headers, app_module, monkeypatch
):
    limit = 1024 * 1024
    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", limit)
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", limit)

    response = client.post(
        "/api/upload",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"x" * (limit + 1024)), "big.mp3"),
            "targetPath": "",
            "originalFilename": "big.mp3",
        },
    )

    assert response.status_code == 413
    assert response.is_json
    assert "too large" in response.get_json()["error"]


def test_oversized_cover_upload_returns_json_413(
    client, auth_headers, music_root, write_library_file, app_module, monkeypatch
):
    target = write_library_file(f"cover-{uuid.uuid4().hex}.mp3")
    monkeypatch.setattr(app_module, "COVER_UPLOAD_BYTES", 1024)

    response = client.post(
        "/api/metadata/picture/file",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"x" * 8192), "cover.jpg"),
            "path": _relative(target, music_root),
        },
    )

    assert response.status_code == 413
    assert response.is_json
    assert "image is too large" in response.get_json()["error"]
