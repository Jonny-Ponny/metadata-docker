"""Shared fixtures for the backend security tests."""

from pathlib import Path
import shutil
import uuid

import pytest


FIXTURES = Path(__file__).resolve().parent / "fixtures"
AUDIO_FIXTURES = FIXTURES / "audio"


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


@pytest.fixture(autouse=True)
def reset_app_state(app_module, monkeypatch):
    """Reset process-wide state so tests cannot leak into each other.

    The login limiter and the version cache are module globals shared by every
    request in the single-worker deployment. Without a reset, one test's five
    failed logins or cached version would change the next test's result.
    """
    with app_module._login_failures_lock:
        app_module._login_failures.clear()

    snapshot = dict(app_module._version_cache)
    yield
    app_module._version_cache.clear()
    app_module._version_cache.update(snapshot)
    with app_module._login_failures_lock:
        app_module._login_failures.clear()


@pytest.fixture
def test_dir(music_root):
    """A unique directory inside the temporary music library."""
    path = music_root / uuid.uuid4().hex
    path.mkdir()
    return path


@pytest.fixture
def fake_fetcher(app_module, monkeypatch):
    """Register a metadata fetcher without touching the addons directory.

    ``register()`` returns the generated class so a test can override one
    method; the monkeypatch removes the entry after the test.
    """

    def register(fetcher_id='fake', **attributes):
        from addon_base import MetadataFetcher

        class Fetcher(MetadataFetcher):
            id = fetcher_id
            name = attributes.pop('name', fetcher_id)
            description = attributes.pop('description', '')
            version = attributes.pop('version', '')
            github = attributes.pop('github', '')
            required_env_vars = attributes.pop('required_env_vars', [])

        for name, value in attributes.items():
            setattr(Fetcher, name, value)

        monkeypatch.setitem(app_module.plugin_manager.fetchers, fetcher_id, Fetcher)
        return Fetcher

    return register


@pytest.fixture
def audio_file(test_dir):
    """Copy a small, valid silent file for an extension into the test folder.

    The fixtures under ``tests/fixtures/audio`` are 0.1 s mono silence files
    generated with ffmpeg, one per supported extension. They keep the tag
    round-trip tests independent of the developer's music library and of
    ffmpeg at test time.
    """

    def _create(extension=".mp3", name=None):
        extension = extension if extension.startswith(".") else f".{extension}"
        source = AUDIO_FIXTURES / f"silence{extension}"
        if not source.is_file():
            raise AssertionError(f"no audio fixture for {extension}")
        destination = test_dir / (name or f"track-{uuid.uuid4().hex}{extension}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    return _create


@pytest.fixture
def write_library_file(music_root):
    """Create a file inside the temporary music library."""

    def _write(relative_path, content=b"audio"):
        path = music_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    return _write
