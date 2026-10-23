"""The version check must be lazy and cache its first result (B-26)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_import_does_not_call_github_and_the_first_check_is_cached(app_module, tmp_path):
    backend_dir = Path(app_module.__file__).resolve().parent
    music = tmp_path / "music"
    logs = tmp_path / "logs"
    work = tmp_path / "work"
    for directory in (music, logs, work):
        directory.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(backend_dir),
            "MUSIC_FOLDER": str(music),
            "LOG_DIR": str(logs),
            "AUTH_USERNAME": "test-admin",
            "AUTH_PASSWORD": "test-password",
            "AUTH_PASSWORD_HASH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.pop("DISABLE_VERSION_CHECK", None)

    script = (
        "import json, requests\n"
        "calls = []\n"
        "def fake_get(*args, **kwargs):\n"
        "    calls.append(args)\n"
        "    raise RuntimeError('network disabled')\n"
        "requests.get = fake_get\n"
        "import app\n"
        "after_import = len(calls)\n"
        "app.get_version_info()\n"
        "first = len(calls)\n"
        "app.get_version_info()\n"
        "print('RESULT=' + json.dumps({\n"
        "    'after_import': after_import,\n"
        "    'after_first': first,\n"
        "    'after_second': len(calls),\n"
        "}))\n"
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
    for line in result.stdout.splitlines():
        if line.startswith("RESULT="):
            data = json.loads(line.split("=", 1)[1])
            break
    else:
        raise AssertionError(f"no result in output: {result.stdout!r}")

    assert data == {"after_import": 0, "after_first": 1, "after_second": 1}


@pytest.mark.parametrize(
    "current,pulled,expected",
    [
        ("v1.0.5", "v1.0.5", False),
        ("1.0.5", "1.0.5", False),
        ("v1.0.5", "v1.0.6", True),
        ("v1.0.5", "v1.1.0", True),
        ("v1.0.5", "v2.0.0", True),
        ("V1.0.5", "V2.0.0", True),
        ("v2.0.0", "v1.9.9", False),
        ("v1.10.0", "v1.9.0", False),
    ],
)
def test_compare_versions_table(app_module, current, pulled, expected):
    assert app_module._compare_versions(current, pulled) is expected


def test_disabled_version_check_makes_no_network_call(
    client, app_module, monkeypatch
):
    def fail(*args, **kwargs):
        raise AssertionError("network must not be used")

    monkeypatch.setattr(app_module, "DISABLE_VERSION_CHECK", True)
    monkeypatch.setattr(app_module.requests, "get", fail)

    response = client.get("/api/version")

    assert response.status_code == 200
    body = response.get_json()
    assert body["latest_version"] is None
    assert body["update_available"] is False


def test_expired_cache_is_refreshed_once(app_module, monkeypatch):
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"tag_name": "v9.9.9"}

    def fake_get(url, timeout=None):
        calls.append(url)
        return Response()

    monkeypatch.setattr(app_module, "DISABLE_VERSION_CHECK", False)
    monkeypatch.setattr(app_module, "CACHE_TTL_SECONDS", 3600)
    monkeypatch.setattr(app_module.requests, "get", fake_get)
    app_module._version_cache.update(
        {"latest": None, "update_available": False, "timestamp": 0}
    )

    first = app_module.get_version_info()
    second = app_module.get_version_info()

    assert first["latest"] == "v9.9.9"
    assert first["update_available"] is True
    assert second == first
    assert len(calls) == 1
