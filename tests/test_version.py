"""The version check must be lazy and cache its first result (B-26)."""

import json
import os
import subprocess
import sys
from pathlib import Path


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
