"""Cache headers for the built SPA.

`index.html` references hashed asset names, so it must be revalidated. If a
browser serves it from cache after an image update, the app keeps running the
previous JS bundle while the backend is new.
"""


def _static_dir(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html>")
    (static / "assets" / "index-abc123.js").write_text("console.log(1)")
    return static


def test_index_html_is_revalidated(client, app_module, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "STATIC_DIR", str(_static_dir(tmp_path)))

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-cache"


def test_hashed_assets_are_immutable(client, app_module, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "STATIC_DIR", str(_static_dir(tmp_path)))

    response = client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["Cache-Control"]


def test_a_non_asset_static_file_is_revalidated(
    client, app_module, tmp_path, monkeypatch
):
    static = _static_dir(tmp_path)
    (static / "favicon.ico").write_bytes(b"icon")
    monkeypatch.setattr(app_module, "STATIC_DIR", str(static))

    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.data == b"icon"
    assert response.headers["Cache-Control"] == "no-cache"


def test_spa_fallback_is_revalidated(client, app_module, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "STATIC_DIR", str(_static_dir(tmp_path)))

    response = client.get("/some/client/route")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-cache"


def test_unknown_api_path_is_not_the_spa(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_missing_asset_is_not_the_spa(client, app_module, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "STATIC_DIR", str(_static_dir(tmp_path)))

    response = client.get("/assets/missing.js")
    assert response.status_code == 404
