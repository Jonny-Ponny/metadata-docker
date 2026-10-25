"""The JSON error handlers and security headers.

The routes in the real app rarely raise on purpose, so these tests build a
small Flask app with the same handlers and trigger each status directly.
"""

import pytest
from flask import Flask, abort, request

import errors


@pytest.fixture
def error_app(monkeypatch):
    limit = 1024 * 1024
    monkeypatch.setattr(errors, "MAX_UPLOAD_BYTES", limit)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = limit
    errors.register_error_handlers(app)

    @app.route("/ok")
    def ok():
        return "ok"

    @app.route("/bad")
    def bad():
        abort(400)

    @app.route("/unsupported")
    def unsupported():
        abort(415)

    @app.route("/boom")
    def boom():
        raise RuntimeError("secret detail")

    @app.route("/generic", methods=["POST"])
    def generic():
        request.get_data()
        return "ok"

    return app


def _assert_security_headers(response):
    assert "'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_an_unhandled_exception_becomes_a_json_500(error_app):
    response = error_app.test_client().get("/boom")

    assert response.status_code == 500
    assert response.is_json
    assert response.get_json() == {
        "error": "An unexpected server error occurred."
    }
    assert b"secret detail" not in response.data
    _assert_security_headers(response)


def test_the_400_handler_returns_json(error_app):
    response = error_app.test_client().get("/bad")

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid request."}
    _assert_security_headers(response)


def test_the_415_handler_returns_json(error_app):
    response = error_app.test_client().get("/unsupported")

    assert response.status_code == 415
    assert response.get_json() == {
        "error": "Unsupported request body; send JSON."
    }
    _assert_security_headers(response)


def test_the_generic_413_branch_names_the_request_limit(error_app):
    response = error_app.test_client().post(
        "/generic", data=b"x" * (1024 * 1024 + 1)
    )

    assert response.status_code == 413
    assert response.get_json() == {
        "error": "The request is too large. The maximum size is 1 MiB."
    }
    _assert_security_headers(response)


def test_security_headers_are_added_to_successful_responses(error_app):
    response = error_app.test_client().get("/ok")

    assert response.status_code == 200
    _assert_security_headers(response)
