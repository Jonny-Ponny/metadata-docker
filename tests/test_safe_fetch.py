"""SSRF guard and streaming limits in ``safe_fetch``.

The module is the only place that talks to arbitrary user-supplied URLs, so
these tests stay entirely offline: DNS and ``requests.get`` are faked.
"""

import socket

import pytest
import requests

import safe_fetch


PUBLIC_IP = "93.184.216.34"
PRIVATE_IP = "10.0.0.5"


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "1.1.1.1",
        "2606:4700:4700::1111",
        "::ffff:8.8.8.8",
    ],
)
def test_public_addresses_are_allowed(address):
    assert safe_fetch._is_public_address(address) is True


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.10",
        "169.254.1.1",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "::",
        "fe80::1",
        "::ffff:127.0.0.1",
        # 6to4 and Teredo can embed a private IPv4 target.
        "2002:7f00:1::",
        "2001:0000:4136:e378:8000:63bf:3fff:fdd2",
        "not-an-address",
    ],
)
def test_private_and_tunnel_addresses_are_rejected(address):
    assert safe_fetch._is_public_address(address) is False


def _resolve_to(monkeypatch, mapping):
    def fake_getaddrinfo(host, port, type=None):
        try:
            addresses = mapping[host]
        except KeyError:
            raise socket.gaierror(f"unknown host {host}")
        if isinstance(addresses, Exception):
            raise addresses
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
            for address in addresses
        ]

    monkeypatch.setattr(safe_fetch.socket, "getaddrinfo", fake_getaddrinfo)


def test_validate_public_url_accepts_a_public_host(monkeypatch):
    _resolve_to(monkeypatch, {"cdn.test": [PUBLIC_IP]})

    parsed = safe_fetch.validate_public_url("https://cdn.test/a/cover.jpg")

    assert parsed.scheme == "https"
    assert parsed.hostname == "cdn.test"


@pytest.mark.parametrize(
    "url,message",
    [
        (123, "URL must be a string"),
        ("ftp://cdn.test/cover.jpg", "Only http and https"),
        ("file:///etc/passwd", "Only http and https"),
        ("https:///cover.jpg", "missing a host"),
        ("https://user:pass@cdn.test/cover.jpg", "embedded credentials"),
        ("https://user@cdn.test/cover.jpg", "embedded credentials"),
        ("http://[::1", "Invalid URL"),
    ],
)
def test_validate_public_url_rejects_unsafe_urls(monkeypatch, url, message):
    _resolve_to(monkeypatch, {"cdn.test": [PUBLIC_IP]})

    with pytest.raises(safe_fetch.UnsafeURLError, match=message):
        safe_fetch.validate_public_url(url)


def test_resolution_failure_is_rejected(monkeypatch):
    _resolve_to(monkeypatch, {"missing.test": socket.gaierror("nope")})

    with pytest.raises(safe_fetch.UnsafeURLError, match="Could not resolve"):
        safe_fetch.validate_public_url("https://missing.test/cover.jpg")


def test_empty_resolution_is_rejected(monkeypatch):
    _resolve_to(monkeypatch, {"empty.test": []})

    with pytest.raises(safe_fetch.UnsafeURLError, match="Could not resolve"):
        safe_fetch.validate_public_url("https://empty.test/cover.jpg")


def test_one_private_address_rejects_the_whole_host(monkeypatch):
    _resolve_to(monkeypatch, {"mixed.test": [PUBLIC_IP, PRIVATE_IP]})

    with pytest.raises(safe_fetch.UnsafeURLError, match="non-public address"):
        safe_fetch.validate_public_url("https://mixed.test/cover.jpg")


class FakeResponse:
    def __init__(self, status_code=200, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = headers or {}
        self.chunks = list(chunks)
        self.closed = False

    def iter_content(self, chunk_size):
        assert chunk_size == safe_fetch._CHUNK_SIZE
        yield from self.chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def close(self):
        self.closed = True


def _install_responses(monkeypatch, responses):
    calls = []
    queue = list(responses)

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return queue.pop(0)

    _resolve_to(monkeypatch, {"cdn.test": [PUBLIC_IP]})
    monkeypatch.setattr(safe_fetch.requests, "get", fake_get)
    return calls


def test_fetch_image_returns_the_body_and_normalised_type(monkeypatch):
    response = FakeResponse(
        headers={
            "Content-Type": "image/png; charset=binary",
            "Content-Length": "6",
        },
        chunks=[b"abc", b"def"],
    )
    calls = _install_responses(monkeypatch, [response])

    data, mime = safe_fetch.fetch_image(
        "https://cdn.test/cover.png", "test-agent/1.0"
    )

    assert data == b"abcdef"
    assert mime == "image/png"
    assert response.closed is True
    assert calls[0][0] == "https://cdn.test/cover.png"
    assert calls[0][1]["headers"] == {"User-Agent": "test-agent/1.0"}
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["timeout"] == (
        safe_fetch.CONNECT_TIMEOUT_SECONDS,
        safe_fetch.READ_TIMEOUT_SECONDS,
    )


def test_fetch_image_rejects_a_non_image_content_type(monkeypatch):
    response = FakeResponse(headers={"Content-Type": "text/html"})
    _install_responses(monkeypatch, [response])

    with pytest.raises(safe_fetch.UnsafeURLError, match="did not return an image"):
        safe_fetch.fetch_image("https://cdn.test/page", "agent")

    assert response.closed is True


def test_declared_content_length_over_the_cap_fails_before_reading(monkeypatch):
    response = FakeResponse(
        headers={"Content-Type": "image/jpeg", "Content-Length": "11"},
    )
    _install_responses(monkeypatch, [response])

    with pytest.raises(safe_fetch.ImageTooLargeError, match="too large"):
        safe_fetch.fetch_image("https://cdn.test/cover.jpg", "agent", max_bytes=10)

    assert response.closed is True


def test_non_numeric_content_length_is_ignored(monkeypatch):
    response = FakeResponse(
        headers={"Content-Type": "image/jpeg", "Content-Length": "unknown"},
        chunks=[b"12345"],
    )
    _install_responses(monkeypatch, [response])

    data, _ = safe_fetch.fetch_image(
        "https://cdn.test/cover.jpg", "agent", max_bytes=10
    )

    assert data == b"12345"
    assert response.closed is True


def test_streamed_body_over_the_cap_fails(monkeypatch):
    response = FakeResponse(
        headers={"Content-Type": "image/jpeg"},
        chunks=[b"123456", b"78901"],
    )
    _install_responses(monkeypatch, [response])

    with pytest.raises(safe_fetch.ImageTooLargeError, match="too large"):
        safe_fetch.fetch_image("https://cdn.test/cover.jpg", "agent", max_bytes=10)

    assert response.closed is True


def test_http_error_is_propagated_and_the_response_is_closed(monkeypatch):
    response = FakeResponse(status_code=404, headers={"Content-Type": "text/html"})
    _install_responses(monkeypatch, [response])

    with pytest.raises(requests.HTTPError):
        safe_fetch.fetch_image("https://cdn.test/missing.jpg", "agent")

    assert response.closed is True


def test_redirect_is_followed_and_revalidated(monkeypatch):
    redirect = FakeResponse(status_code=302, headers={"Location": "/real.png"})
    image = FakeResponse(
        headers={"Content-Type": "image/png"}, chunks=[b"png"]
    )
    calls = _install_responses(monkeypatch, [redirect, image])

    data, mime = safe_fetch.fetch_image(
        "https://cdn.test/start", "agent"
    )

    assert data == b"png"
    assert mime == "image/png"
    assert [call[0] for call in calls] == [
        "https://cdn.test/start",
        "https://cdn.test/real.png",
    ]
    assert redirect.closed is True
    assert image.closed is True


def test_redirect_without_a_location_is_rejected(monkeypatch):
    response = FakeResponse(status_code=302)
    _install_responses(monkeypatch, [response])

    with pytest.raises(safe_fetch.UnsafeURLError, match="no Location"):
        safe_fetch.fetch_image("https://cdn.test/start", "agent")

    assert response.closed is True


def test_too_many_redirects_is_rejected(monkeypatch):
    first = FakeResponse(status_code=301, headers={"Location": "/two"})
    second = FakeResponse(status_code=301, headers={"Location": "/three"})
    _install_responses(monkeypatch, [first, second])

    with pytest.raises(safe_fetch.UnsafeURLError, match="Too many redirects"):
        safe_fetch.fetch_image(
            "https://cdn.test/one", "agent", max_redirects=1
        )

    assert first.closed is True
    assert second.closed is True


def test_a_redirect_to_a_private_host_is_rejected(monkeypatch):
    redirect = FakeResponse(
        status_code=307, headers={"Location": "http://internal.test/secret"}
    )
    calls = _install_responses(monkeypatch, [redirect])
    _resolve_to(
        monkeypatch,
        {"cdn.test": [PUBLIC_IP], "internal.test": [PRIVATE_IP]},
    )

    with pytest.raises(safe_fetch.UnsafeURLError, match="non-public address"):
        safe_fetch.fetch_image("https://cdn.test/start", "agent")

    assert len(calls) == 1
    assert redirect.closed is True
