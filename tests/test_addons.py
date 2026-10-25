"""Addon URL validation, result-limit clamping and plugin discovery (B-24, B-25)."""

import textwrap

import pytest

def test_addon_github_url_accepts_https(app_module):
    class Fetcher:
        github = "https://github.com/user/repo"

    assert app_module._addon_github_url(Fetcher) == "https://github.com/user/repo"


def test_addon_github_url_adds_the_scheme_for_a_bare_host(app_module):
    class Fetcher:
        github = "github.com/user/repo"

    assert app_module._addon_github_url(Fetcher) == "https://github.com/user/repo"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/user/repo",
        "https://user:pass@github.com/user/repo",
        "https://gitlab.com/user/repo",
        "ftp://github.com/user/repo",
        "javascript:alert(1)",
        "",
    ],
)
def test_addon_github_url_rejects_unsafe_values(app_module, url):
    class Fetcher:
        github = url

    assert app_module._addon_github_url(Fetcher) == ""


@pytest.mark.parametrize(
    "endpoint,method",
    [
        ("search_songs", "search_songs"),
        ("search_albums", "search_albums"),
    ],
)
def test_addon_limit_is_clamped(
    client, auth_headers, app_module, monkeypatch, endpoint, method
):
    captured = []

    class Fetcher:
        id = "fake"

    def search(self, query, limit):
        captured.append(limit)
        return []

    setattr(Fetcher, method, search)
    monkeypatch.setitem(app_module.plugin_manager.fetchers, "fake", Fetcher)

    for requested, expected in (("0", 1), ("-1", 1), ("10000", 50), ("7", 7)):
        response = client.get(
            f"/api/addons/fake/{endpoint}",
            headers=auth_headers,
            query_string={"query": "test", "limit": requested},
        )

        assert response.status_code == 200, requested

    assert captured == [1, 1, 50, 7]


def _entry(response, fetcher_id):
    entries = response.get_json()["fetchers"]
    return next(entry for entry in entries if entry["id"] == fetcher_id)


def test_list_addons_reports_the_declared_metadata(
    client, auth_headers, fake_fetcher
):
    def search_songs(self, query, limit):
        return []

    fake_fetcher(
        "fake",
        name="Fake Fetcher",
        description="Looks things up",
        version=" 1.2 ",
        github="https://github.com/user/repo",
        required_env_vars=["API_KEY"],
        search_songs=search_songs,
    )

    response = client.get("/api/addons", headers=auth_headers)

    assert response.status_code == 200
    entry = _entry(response, "fake")
    assert entry["name"] == "Fake Fetcher"
    assert entry["description"] == "Looks things up"
    assert entry["version"] == "1.2"
    assert entry["github"] == "https://github.com/user/repo"
    assert entry["required_env_vars"] == ["API_KEY"]
    # Only the overridden method is advertised; inherited ones raise
    # NotImplementedError and must not appear.
    assert entry["methods"] == ["search_songs"]


def test_list_addons_skips_a_fetcher_that_cannot_initialize(
    client, auth_headers, app_module, monkeypatch
):
    class Broken:
        id = "broken"
        name = "Broken"

        def __init__(self):
            raise RuntimeError("missing configuration")

    monkeypatch.setitem(app_module.plugin_manager.fetchers, "broken", Broken)

    response = client.get("/api/addons", headers=auth_headers)

    assert response.status_code == 200
    assert all(
        entry["id"] != "broken" for entry in response.get_json()["fetchers"]
    )


def test_search_results_normalise_legacy_field_names(
    client, auth_headers, fake_fetcher
):
    def search_songs(self, query, limit):
        return [
            {
                "title": "Song",
                "year": "1999",
                "track": "7",
                "disk": "1",
                "extra_info": "note",
            }
        ]

    fake_fetcher("legacy", search_songs=search_songs)

    response = client.get(
        "/api/addons/legacy/search_songs",
        headers=auth_headers,
        query_string={"query": "song"},
    )

    assert response.status_code == 200
    result = response.get_json()["results"][0]
    assert result == {
        "title": "Song",
        "date": "1999",
        "trackNumber": "7",
        "diskNumber": "1",
        "extraInfo": "note",
    }


def test_fetch_album_normalises_every_track(client, auth_headers, fake_fetcher):
    def fetch_album_metadata(self, album_id):
        return [{"year": "2001"}, {"track": "2", "title": "Second"}]

    fake_fetcher("albums", fetch_album_metadata=fetch_album_metadata)

    response = client.get(
        "/api/addons/albums/fetch_album/42",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["metadata"] == [
        {"date": "2001"},
        {"trackNumber": "2", "title": "Second"},
    ]


def test_fetch_song_normalises_the_result(client, auth_headers, fake_fetcher):
    fake_fetcher(
        "songs",
        fetch_song_metadata=lambda self, song_id: {
            "title": "Track",
            "disk": "1",
        },
    )

    response = client.get(
        "/api/addons/songs/fetch_song/7",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["metadata"] == {
        "title": "Track",
        "diskNumber": "1",
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/addons/plain/search_songs?query=x",
        "/api/addons/plain/search_albums?query=x",
        "/api/addons/plain/fetch_song/1",
        "/api/addons/plain/fetch_album/1",
    ],
)
def test_unimplemented_addon_methods_return_a_json_400(
    client, auth_headers, fake_fetcher, path
):
    fake_fetcher("plain")

    response = client.get(path, headers=auth_headers)

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert "not supported" in response.get_json()["error"].lower()


@pytest.mark.parametrize(
    "path",
    [
        "/api/addons/failing/search_songs?query=x",
        "/api/addons/failing/fetch_song/1",
        "/api/addons/failing/search_albums?query=x",
        "/api/addons/failing/fetch_album/1",
    ],
)
def test_a_failing_addon_returns_a_json_error(
    client, auth_headers, fake_fetcher, path
):
    def fail(*args, **kwargs):
        raise RuntimeError("provider is down")

    fake_fetcher(
        "failing",
        search_songs=fail,
        fetch_song_metadata=fail,
        search_albums=fail,
        fetch_album_metadata=fail,
    )

    response = client.get(path, headers=auth_headers)

    assert response.status_code == 500
    body = response.get_json()
    assert body["success"] is False
    assert body["error"] == "The addon failed to complete the request."


@pytest.mark.parametrize(
    "path",
    [
        "/api/addons/plain/search_songs",
        "/api/addons/plain/search_albums",
    ],
)
def test_addon_search_requires_a_query(client, auth_headers, fake_fetcher, path):
    fake_fetcher("plain")

    response = client.get(path, headers=auth_headers)

    assert response.status_code == 400
    assert response.get_json()["success"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/api/addons/missing/search_songs?query=x",
        "/api/addons/missing/fetch_song/1",
        "/api/addons/missing/search_albums?query=x",
        "/api/addons/missing/fetch_album/1",
    ],
)
def test_unknown_addon_returns_404(client, auth_headers, path):
    response = client.get(path, headers=auth_headers)

    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_plugin_discovery_ignores_private_and_broken_modules(tmp_path):
    from plugin_manager import PluginManager

    addons = tmp_path / "addons"
    addons.mkdir()
    (addons / "_private.py").write_text(
        textwrap.dedent(
            """
            from addon_base import MetadataFetcher

            class Hidden(MetadataFetcher):
                id = 'hidden'
                name = 'Hidden'
            """
        )
    )
    (addons / "broken.py").write_text("raise ImportError('broken addon')\n")
    (addons / "good.py").write_text(
        textwrap.dedent(
            """
            from addon_base import MetadataFetcher

            class Good(MetadataFetcher):
                id = 'good'
                name = 'Good'
            """
        )
    )

    manager = PluginManager(addons_dir=str(addons))
    manager.discover_plugins()

    assert set(manager.fetchers) == {"good"}


def test_duplicate_fetcher_ids_keep_the_last_definition(tmp_path):
    from plugin_manager import PluginManager

    addons = tmp_path / "addons"
    addons.mkdir()
    (addons / "duplicates.py").write_text(
        textwrap.dedent(
            """
            from addon_base import MetadataFetcher

            class First(MetadataFetcher):
                id = 'duplicate'
                name = 'First'

            class Second(MetadataFetcher):
                id = 'duplicate'
                name = 'Second'
            """
        )
    )

    manager = PluginManager(addons_dir=str(addons))
    manager.discover_plugins()

    assert manager.fetchers["duplicate"].name == "Second"


def test_list_addons_reports_all_implemented_methods(
    client, auth_headers, fake_fetcher
):
    fake_fetcher(
        "everything",
        search_albums=lambda self, query, limit: [],
        fetch_album_metadata=lambda self, album_id: {},
        search_songs=lambda self, query, limit: [],
        fetch_song_metadata=lambda self, song_id: {},
    )

    response = client.get("/api/addons", headers=auth_headers)

    assert response.status_code == 200
    assert _entry(response, "everything")["methods"] == [
        "search_albums",
        "fetch_album_metadata",
        "search_songs",
        "fetch_song_metadata",
    ]


def test_legacy_keys_only_replace_empty_current_values():
    from routes.addons import _normalize_addon_metadata

    assert _normalize_addon_metadata(
        {"date": "new", "year": "old", "title": "Song"}
    ) == {"date": "new", "year": "old", "title": "Song"}
    assert _normalize_addon_metadata(
        {"date": "", "year": "old"}
    ) == {"date": "old"}
    assert _normalize_addon_metadata(["not", "a", "dict"]) == [
        "not",
        "a",
        "dict",
    ]


def test_addon_github_url_accepts_www_and_alternate_attributes():
    from routes.addons import _addon_github_url

    class Www:
        github = "www.github.com/user/repo"

    class Alternate:
        repository = "https://github.com/user/other"

    assert _addon_github_url(Www) == "https://www.github.com/user/repo"
    assert _addon_github_url(Alternate) == "https://github.com/user/other"


def test_addon_version_is_normalised():
    from routes.addons import _addon_version

    class NoneVersion:
        version = None

    class NumberVersion:
        version = 42

    assert _addon_version(NoneVersion) == ""
    assert _addon_version(NumberVersion) == "42"


def test_reload_plugins_picks_up_new_addons(tmp_path):
    from plugin_manager import PluginManager

    addons = tmp_path / "addons"
    addons.mkdir()
    (addons / "first.py").write_text(
        textwrap.dedent(
            """
            from addon_base import MetadataFetcher

            class First(MetadataFetcher):
                id = 'first'
                name = 'First'
            """
        )
    )
    manager = PluginManager(addons_dir=str(addons))
    manager.discover_plugins()
    assert set(manager.fetchers) == {"first"}

    (addons / "second.py").write_text(
        textwrap.dedent(
            """
            from addon_base import MetadataFetcher

            class Second(MetadataFetcher):
                id = 'second'
                name = 'Second'
            """
        )
    )
    manager.reload_plugins()

    assert set(manager.fetchers) == {"first", "second"}

