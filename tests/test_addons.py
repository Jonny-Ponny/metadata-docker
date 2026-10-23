"""Addon URL validation and result-limit clamping (B-24, B-25)."""

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
