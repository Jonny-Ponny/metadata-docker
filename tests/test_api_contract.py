"""JSON body handling shared by every API route (B-08).

Before the ``_json_object()`` helper, a missing/wrong ``Content-Type`` made
Flask answer with an HTML 415 page, malformed JSON with an HTML 400 page, and
a JSON list or string reached ``data.get()`` and produced a 500.
"""

import pytest


ROUTES = [
    "/api/metadata/file",
    "/api/metadata/folder",
    "/api/metadata/folder/current",
    "/api/metadata/field/delete",
    "/api/metadata/picture/url",
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
