"""Shared fixtures for the backend security tests."""

from pathlib import Path
import uuid

import pytest


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    """Import the Flask app once with an isolated library and log directory."""
    root = tmp_path_factory.mktemp("metadata-app")
    music = root / "music"
    logs = root / "logs"
    work = root / "work"
    for directory in (music, logs, work):
        directory.mkdir()

    env = {
        "MUSIC_FOLDER": str(music),
        "LOG_DIR": str(logs),
        "DISABLE_VERSION_CHECK": "true",
        "AUTH_USERNAME": "test-admin",
        "AUTH_PASSWORD": "test-password",
        "AUTH_PASSWORD_HASH": "",
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    # Environment variables must be set before importing app: the module reads
    # them at import time and starts the plugin manager relative to the CWD.
    with pytest.MonkeyPatch.context() as monkeypatch:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.chdir(work)

        import app

        yield app


@pytest.fixture(scope="session")
def music_root(app_module):
    return Path(app_module.MUSIC_ROOT)


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/login",
        json={"username": "test-admin", "password": "test-password"},
    )
    assert response.status_code == 200, response.data

    token = response.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_dir(music_root):
    """A unique directory inside the temporary music library."""
    path = music_root / uuid.uuid4().hex
    path.mkdir()
    return path


@pytest.fixture
def write_library_file(music_root):
    """Create a file inside the temporary music library."""

    def _write(relative_path, content=b"audio"):
        path = music_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    return _write
