"""Authentication, token scopes and the login rate limiter."""

import datetime

import jwt
import pytest

import auth


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


def test_constant_time_eq_matches_only_identical_strings():
    import auth

    assert auth._constant_time_eq("abc", "abc") is True
    assert auth._constant_time_eq("abc", "abd") is False
    assert auth._constant_time_eq("abc", "abcd") is False


def test_password_matches_plain_and_hashed_configuration(monkeypatch):
    from werkzeug.security import generate_password_hash

    import auth

    monkeypatch.setattr(auth, "AUTH_PASSWORD_HASH", "")
    assert auth._password_matches("test-password") is True
    assert auth._password_matches("wrong-password") is False

    monkeypatch.setattr(
        auth, "AUTH_PASSWORD_HASH", generate_password_hash("hashed-password")
    )
    assert auth._password_matches("hashed-password") is True
    assert auth._password_matches("test-password") is False


def test_reset_rate_limiter_forgets_failures(client, app_module):
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS):
        _login(client, "wrong-password")
    assert _login(client, "wrong-password").status_code == 429

    app_module.reset_rate_limiter()

    assert _login(client, "wrong-password").status_code == 401


def _session_token(app_module, **overrides):
    claims = {
        "username": app_module.AUTH_USERNAME,
        "scope": app_module.TOKEN_SCOPE_SESSION,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(
        claims, app_module.app.config["SECRET_KEY"], algorithm="HS256"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"username": "someone-else"},
        {"scope": "download"},
        {"scope": None},
        {"username": None},
    ],
)
def test_session_tokens_with_the_wrong_claims_are_rejected(
    client, app_module, overrides
):
    token = _session_token(app_module, **overrides)

    response = client.get(
        "/api/validate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_a_session_token_cannot_be_used_as_a_download_token(
    client, auth_headers
):
    token = auth_headers["Authorization"].split(" ", 1)[1]

    response = client.get("/api/download", query_string={"token": token})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is invalid"


def test_oversized_login_credentials_are_rejected(client):
    for username, password in (("a" * 257, "x"), ("test-admin", "x" * 4097)):
        response = client.post(
            "/api/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 401
        assert response.get_json()["error"] == "Invalid credentials"


def test_login_requires_a_json_object(client):
    response = client.post("/api/login", json=["test-admin", "test-password"])

    assert response.status_code == 400
    assert response.get_json()["error"] == "Username and password required"


def test_a_corrupt_password_hash_never_matches(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_PASSWORD_HASH", "not-a-valid-hash")

    assert auth._password_matches("anything") is False


def test_lockout_expires_after_the_window(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "time", lambda: clock[0])
    ip = "203.0.113.10"

    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        retry_after = auth._record_login_failure(ip)

    assert retry_after == auth.LOGIN_LOCKOUT_SECONDS
    assert auth._login_retry_after(ip) > 0

    clock[0] += auth.LOGIN_LOCKOUT_SECONDS + 1

    assert auth._login_retry_after(ip) == 0
    assert ip not in auth._login_failures


def test_failures_start_a_new_window_after_the_lockout(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "time", lambda: clock[0])
    ip = "203.0.113.11"

    for _ in range(auth.LOGIN_MAX_ATTEMPTS - 1):
        assert auth._record_login_failure(ip) == 0

    clock[0] += auth.LOGIN_LOCKOUT_SECONDS + 1

    # The old count is discarded, so this is the first failure of a new window.
    assert auth._record_login_failure(ip) == 0
    assert auth._login_failures[ip]["count"] == 1


def test_the_limiter_is_per_client_address(monkeypatch):
    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)

    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        auth._record_login_failure("203.0.113.12")

    assert auth._login_retry_after("203.0.113.12") > 0
    assert auth._login_retry_after("203.0.113.13") == 0


def test_the_failure_table_is_pruned(monkeypatch):
    now = 10000.0
    monkeypatch.setattr(auth.time, "time", lambda: now)
    auth._login_failures.update(
        {
            f"stale-{index}": {"count": 1, "first": 0, "locked_until": 0}
            for index in range(4097)
        }
    )

    auth._record_login_failure("203.0.113.14")

    assert set(auth._login_failures) == {"203.0.113.14"}
