"""Shared fixtures for the backend security tests."""

from pathlib import Path
import atexit
import os
import shutil
import tempfile
import uuid

import pytest


FIXTURES = Path(__file__).resolve().parent / "fixtures"
AUDIO_FIXTURES = FIXTURES / "audio"

# The environment has to be in place before *any* backend module is imported,
# not just before the app fixture runs. ``config.py`` reads every value once at
# import time, and test modules import backend helpers (``paths``,
# ``zip_stream``, ...) during collection, which pulls ``config`` in through the
# ``errors`` module. Setting the variables here — conftest is imported before
# the test modules — keeps that order-independent.
SESSION_ROOT = Path(tempfile.mkdtemp(prefix="metadata-tests-"))
atexit.register(shutil.rmtree, SESSION_ROOT, ignore_errors=True)
for _directory in ("music", "logs", "work"):
    (SESSION_ROOT / _directory).mkdir()

os.environ.update({
    "MUSIC_FOLDER": str(SESSION_ROOT / "music"),
    "LOG_DIR": str(SESSION_ROOT / "logs"),
    "DISABLE_VERSION_CHECK": "true",
    "AUTH_USERNAME": "test-admin",
    "AUTH_PASSWORD": "test-password",
    "AUTH_PASSWORD_HASH": "",
    "PYTHONDONTWRITEBYTECODE": "1",
})


@pytest.fixture(scope="session")
def app_module():
    """Import the Flask app once with an isolated library and log directory."""
    # The plugin manager is discovered relative to the CWD, so the import has to
    # happen from the throwaway work directory.
    work = SESSION_ROOT / "work"
    previous = os.getcwd()
    os.chdir(work)
    try:
        import app

        yield app
    finally:
        os.chdir(previous)


@pytest.fixture(scope="session")
def logs_module(app_module):
    """The blueprint module that owns the log routes."""
    from routes import logs

    return logs


@pytest.fixture(scope="session")
def tags_module(app_module):
    """The blueprint module that owns metadata, cover and media routes."""
    from routes import tags

    return tags


@pytest.fixture(scope="session")
def system_module(app_module):
    """The blueprint module that owns the version cache and the health check."""
    from routes import system

    return system


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
    app_module.reset_rate_limiter()

    snapshot = dict(app_module._version_cache)
    yield
    app_module._version_cache.clear()
    app_module._version_cache.update(snapshot)
    app_module.reset_rate_limiter()


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
