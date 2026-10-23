"""Authentication, token scopes and the login rate limiter."""

import datetime

import jwt
import pytest


def _login(client, password):
    return client.post(
        "/api/login",
        json={"username": "test-admin", "password": password},
    )


def test_five_failures_lock_the_client_out(client, app_module):
    for attempt in range(1, app_module.LOGIN_MAX_ATTEMPTS):
        response = _login(client, "wrong-password")
        assert response.status_code == 401, attempt

    response = _login(client, "wrong-password")

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) == app_module.LOGIN_LOCKOUT_SECONDS
    assert response.is_json

    # The lockout applies even to the correct password.
    assert _login(client, "test-password").status_code == 429


def test_successful_login_clears_the_failure_counter(client, app_module):
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS - 1):
        assert _login(client, "wrong-password").status_code == 401

    assert _login(client, "test-password").status_code == 200

    # If the counter had not been cleared, the next attempt would be a 429.
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS - 1):
        assert _login(client, "wrong-password").status_code == 401


def test_login_rejects_missing_and_non_string_credentials(client):
    assert client.post("/api/login", json={}).status_code == 400
    assert _login(client, None).status_code == 400
    assert _login(client, 123).status_code == 400


def test_expired_session_token_is_rejected(client, app_module):
    token = jwt.encode(
        {
            "username": app_module.AUTH_USERNAME,
            "scope": app_module.TOKEN_SCOPE_SESSION,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=1),
        },
        app_module.app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    response = client.get(
        "/api/validate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token has expired"


def test_tampered_signature_is_rejected(client, auth_headers):
    token = auth_headers["Authorization"].split(" ", 1)[1]
    header, payload, signature = token.split(".")
    tampered = ".".join((header, payload, signature[:-1] + ("A" if signature[-1] != "A" else "B")))

    response = client.get(
        "/api/validate",
        headers={"Authorization": f"Bearer {tampered}"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_download_token_cannot_authorize_session_routes(
    client, auth_headers, music_root, test_dir
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = client.post(
        "/api/download-token",
        headers=auth_headers,
        json={"path": song.relative_to(music_root).as_posix()},
    )
    assert response.status_code == 200
    download_token = response.get_json()["token"]

    response = client.get(
        "/api/validate",
        headers={"Authorization": f"Bearer {download_token}"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer "])
def test_missing_or_malformed_authorization_header_is_rejected(
    client, authorization
):
    headers = {} if authorization is None else {"Authorization": authorization}

    response = client.get("/api/validate", headers=headers)

    assert response.status_code == 401
    assert response.is_json
