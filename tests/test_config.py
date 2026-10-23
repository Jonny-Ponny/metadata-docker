"""Invalid integer environment variables must not crash the app (B-09).

``TOKEN_EXPIRE_HOURS`` and ``CACHE_TTL_SECONDS`` used bare ``int(os.getenv())``
calls, so a typo in the compose file raised ``ValueError`` before Flask started.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


DEFAULTS = {
    "TOKEN_EXPIRE_HOURS": 12,
    "CACHE_TTL_SECONDS": 3600,
    "MAX_UPLOAD_MB": 4096,
}


def _import_with_env(app_module, root, overrides):
    backend_dir = Path(app_module.__file__).resolve().parent
    music = root / "music"
    logs = root / "logs"
    work = root / "work"
    for directory in (music, logs, work):
        directory.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(backend_dir),
            "MUSIC_FOLDER": str(music),
            "LOG_DIR": str(logs),
            "DISABLE_VERSION_CHECK": "true",
            "AUTH_USERNAME": "test-admin",
            "AUTH_PASSWORD": "test-password",
            "AUTH_PASSWORD_HASH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.update(overrides)

    script = (
        "import json, app; "
        "print('RESULT=' + json.dumps({"
        "'TOKEN_EXPIRE_HOURS': app.TOKEN_EXPIRE_HOURS, "
        "'CACHE_TTL_SECONDS': app.CACHE_TTL_SECONDS, "
        "'MAX_UPLOAD_MB': app.MAX_UPLOAD_BYTES // (1024 * 1024)"
        "}))"
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
            return json.loads(line.split("=", 1)[1])
    raise AssertionError(f"no result in output: {result.stdout!r}")


@pytest.mark.parametrize("name", sorted(DEFAULTS))
@pytest.mark.parametrize("value", ["abc", "0", "-5", "12x"])
def test_invalid_integer_env_falls_back_to_the_default(
    app_module, tmp_path, name, value
):
    result = _import_with_env(app_module, tmp_path, {name: value})

    assert result[name] == DEFAULTS[name]


@pytest.mark.parametrize(
    "name,value",
    [
        ("TOKEN_EXPIRE_HOURS", 48),
        ("CACHE_TTL_SECONDS", 90),
        ("MAX_UPLOAD_MB", 10),
    ],
)
def test_valid_integer_env_is_used(app_module, tmp_path, name, value):
    result = _import_with_env(app_module, tmp_path, {name: str(value)})

    assert result[name] == value
