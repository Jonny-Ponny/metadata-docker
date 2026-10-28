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
from werkzeug.security import generate_password_hash


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
            "JWT_SECRET": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.update(overrides)

    script = (
        "import json, app; "
        "print('RESULT=' + json.dumps({"
        "'TOKEN_EXPIRE_HOURS': app.TOKEN_EXPIRE_HOURS, "
        "'CACHE_TTL_SECONDS': app.CACHE_TTL_SECONDS, "
        "'MAX_UPLOAD_MB': app.MAX_UPLOAD_BYTES // (1024 * 1024), "
        "'AUTH_USERNAME': app.AUTH_USERNAME, "
        "'AUTH_PASSWORD': app.AUTH_PASSWORD, "
        "'AUTH_PASSWORD_HASH': app.AUTH_PASSWORD_HASH, "
        "'JWT_SECRET_KEY': app.JWT_SECRET_KEY"
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


def test_installed_flask_supports_per_request_upload_limits():
    """Cover uploads assign request.max_content_length (B-29)."""
    from importlib.metadata import version
    import re

    match = re.match(r"(\d+)\.(\d+)", version("flask"))
    assert match, version("flask")
    assert tuple(int(part) for part in match.groups()) >= (3, 1)


def test_invalid_password_hash_generates_a_temporary_password(
    app_module, tmp_path
):
    """A bad hash must not crash-loop the container (B-31)."""
    result = _import_with_env(
        app_module,
        tmp_path,
        {
            "AUTH_PASSWORD_HASH": "not-a-valid-hash",
            "AUTH_PASSWORD": "configured-password",
        },
    )

    assert result["AUTH_PASSWORD_HASH"] == ""
    assert result["AUTH_PASSWORD"]
    assert result["AUTH_PASSWORD"] != "configured-password"

    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "not a valid Werkzeug password hash" in log
    assert "Temporary credentials for this run" in log
    assert f"password: {result['AUTH_PASSWORD']} (generated)" in log


def test_valid_password_hash_is_used_instead_of_the_plaintext(
    app_module, tmp_path
):
    password_hash = generate_password_hash("hashed-password")
    result = _import_with_env(
        app_module,
        tmp_path,
        {
            "AUTH_PASSWORD_HASH": password_hash,
            "AUTH_PASSWORD": "ignored-password",
        },
    )

    assert result["AUTH_PASSWORD_HASH"] == password_hash
    assert result["AUTH_PASSWORD"] == ""


def test_configured_jwt_secret_is_used(app_module, tmp_path):
    """A stable secret keeps sessions valid across restarts (T-11)."""
    secret = "a" * 64
    result = _import_with_env(app_module, tmp_path, {"JWT_SECRET": secret})

    assert result["JWT_SECRET_KEY"] == secret


def test_jwt_secret_at_minimum_length_is_used(app_module, tmp_path):
    secret = "b" * 32
    result = _import_with_env(app_module, tmp_path, {"JWT_SECRET": secret})

    assert result["JWT_SECRET_KEY"] == secret


def test_jwt_secret_is_random_when_unset(app_module, tmp_path):
    first = _import_with_env(app_module, tmp_path, {"JWT_SECRET": ""})
    second = _import_with_env(app_module, tmp_path, {"JWT_SECRET": ""})

    assert first["JWT_SECRET_KEY"] != second["JWT_SECRET_KEY"]
    assert len(first["JWT_SECRET_KEY"]) == 48


@pytest.mark.parametrize("secret", ["too-short", "c" * 31])
def test_short_jwt_secret_is_ignored(app_module, tmp_path, secret):
    result = _import_with_env(app_module, tmp_path, {"JWT_SECRET": secret})

    assert result["JWT_SECRET_KEY"] != secret
    assert len(result["JWT_SECRET_KEY"]) == 48

    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "JWT_SECRET is shorter than 32 characters" in log
