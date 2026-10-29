"""JSON body handling shared by every API route (B-08).

Before the ``_json_object()`` helper, a missing/wrong ``Content-Type`` made
Flask answer with an HTML 415 page, malformed JSON with an HTML 400 page, and
a JSON list or string reached ``data.get()`` and produced a 500.
"""

import pytest

import errors


PUBLIC_ENDPOINTS = {
    ("GET", "/api/ping"),
    ("GET", "/api/version"),
    ("POST", "/api/login"),
    # Authorized by the short-lived token in the query string, not a Bearer
    # header (see tests/test_downloads.py).
    ("GET", "/api/download"),
}

ROUTES = [
    "/api/metadata/file",
    "/api/metadata/folder",
    "/api/metadata/folder/current",
    "/api/metadata/field/delete",
    "/api/metadata/picture/url",
    "/api/metadata/picture/url/folder",
    "/api/metadata/picture/url/folder/current",
    "/api/metadata/picture/delete",
    "/api/metadata/picture/save-as-file",
    "/api/mkdir",
    "/api/rename",
    "/api/move",
    "/api/copy",
    "/api/delete",
    "/api/apply-renaming-scheme",
    "/api/download-token",
    "/api/download",
    "/api/text/save",
]

BAD_BODIES = [
    pytest.param({}, 415, id="no-body"),
    pytest.param(
        {"data": "not json", "content_type": "text/plain"},
        415,
        id="text-plain",
    ),
    pytest.param(
        {"data": "{", "content_type": "application/json"},
        400,
        id="malformed-json",
    ),
    pytest.param({"json": []}, 400, id="json-list"),
    pytest.param({"json": "x"}, 400, id="json-string"),
]


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("body,status", BAD_BODIES)
def test_json_routes_reject_invalid_bodies(
    client, auth_headers, path, body, status
):
    response = client.post(path, headers=auth_headers, **body)

    assert response.status_code == status
    assert response.is_json
    assert "error" in response.get_json()


def test_every_api_route_except_the_public_ones_requires_a_token(
    client, app_module
):
    """A newly added route must opt in to being public.

    Walking ``app.url_map`` means a route added without ``@token_required``
    fails this test instead of silently serving data.
    """
    checked = set()

    for rule in app_module.app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        methods = rule.methods - {"HEAD", "OPTIONS"}
        for method in sorted(methods):
            if (method, rule.rule) in PUBLIC_ENDPOINTS:
                continue

            path = (
                rule.rule.replace("<fetcher_id>", "fake")
                .replace("<song_id>", "1")
                .replace("<album_id>", "1")
            )
            response = client.open(path, method=method)

            assert response.status_code == 401, (method, rule.rule)
            assert response.is_json, (method, rule.rule)
            checked.add((method, rule.rule))

    # The table is useful only if the walk actually found the protected routes.
    assert ("GET", "/api/files") in checked
    assert ("POST", "/api/upload") in checked


def test_security_headers_are_present_on_a_normal_response(client):
    response = client.get("/api/ping")

    assert response.status_code == 200
    assert "'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in response.headers["Permissions-Policy"]


@pytest.mark.parametrize(
    "path",
    ["/api", "/api/does-not-exist", "/api/does/not/exist", "/api/files/extra"],
)
def test_unknown_api_paths_are_json_404_without_the_spa(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json() == {"success": False, "error": "Not found"}


@pytest.mark.parametrize(
    "exc,expected_status,expected_message",
    [
        (PermissionError("secret path"), 403, "Permission denied while accessing the library."),
        (FileNotFoundError("secret path"), 404, "The requested file or folder no longer exists."),
        (OSError(21, "is a folder"), 400, "The requested path is a folder, not a file."),
        (OSError(20, "not a folder"), 400, "The requested path is not a folder."),
        (OSError(17, "exists"), 409, "The destination already exists."),
        (OSError(28, "full"), 500, "The server is out of disk space."),
        (OSError(30, "read-only"), 500, "The filesystem is read-only."),
        (OSError(24, "too many files"), 503, "The server is temporarily unable to open more files."),
        (ValueError("boom"), 500, "fallback"),
    ],
)
def test_public_error_message_table(
    app_module, exc, expected_status, expected_message
):
    message, status = errors._public_error_message(exc, "fallback")

    assert (message, status) == (expected_message, expected_status)


def test_public_error_message_keeps_the_access_denied_text(app_module):
    message, status = errors._public_error_message(
        errors.AccessDenied("Path is outside the music library."),
        "fallback",
    )

    assert (message, status) == (
        "Path is outside the music library.",
        403,
    )


def test_public_error_message_maps_network_errors(app_module):
    import requests

    message, status = errors._public_error_message(
        requests.exceptions.Timeout("slow"), "fallback"
    )
    assert (message, status) == (
        "The external service did not respond in time.",
        504,
    )

    message, status = errors._public_error_message(
        requests.exceptions.ConnectionError("down"), "fallback"
    )
    assert (message, status) == ("The external service request failed.", 502)



def test_create_app_builds_an_equivalent_application(app_module):
    """The factory must register the same routes as the module-level app."""
    other = app_module.create_app({"TESTING": True})

    assert other is not app_module.app
    assert other.config["TESTING"] is True
    assert {rule.rule for rule in other.url_map.iter_rules()} == {
        rule.rule for rule in app_module.app.url_map.iter_rules()
    }
    assert other.test_client().get("/api/ping").status_code == 200
