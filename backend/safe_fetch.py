"""Fetch remote images with a minimal SSRF guard.

Only http/https URLs that resolve exclusively to public addresses are allowed.
Redirects are followed manually so every hop is re-checked, and the body is
streamed into memory with a hard size cap and timeouts.

Residual risk: we validate the resolved addresses and then let ``requests``
resolve the name again when it connects (DNS rebinding). Closing that window
would mean pinning the connection to a validated IP, which is not worth the
complexity for the authenticated cover-art and preview endpoints. The image
content-type requirement also limits what an attacker can exfiltrate through
the response.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_REDIRECTS = 3
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 15
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_CHUNK_SIZE = 64 * 1024


class UnsafeURLError(ValueError):
    """Raised when a URL is not a public http/https URL."""


class ImageTooLargeError(ValueError):
    """Raised when the remote image exceeds the size limit."""


def _is_public_address(address):
    """Return True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    # Unwrap IPv4-mapped/compatible IPv6 so ::ffff:127.0.0.1 is caught.
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None or ip.teredo is not None:
            # 6to4/Teredo tunnel addresses can embed a private IPv4 target.
            return False

    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_unspecified
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_private
        and not ip.is_reserved
    )


def _resolve_public_ips(host):
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise UnsafeURLError(f'Could not resolve host: {host}')

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeURLError(f'Could not resolve host: {host}')

    for address in addresses:
        if not _is_public_address(address):
            raise UnsafeURLError('URL points to a non-public address')
    return addresses


def validate_public_url(url):
    """Validate scheme, host and resolved addresses; raise UnsafeURLError."""
    if not isinstance(url, str):
        raise UnsafeURLError('URL must be a string')

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        # Malformed bracketed IPv6 literals and similar parse failures.
        raise UnsafeURLError('Invalid URL')

    if parsed.scheme not in ('http', 'https'):
        raise UnsafeURLError('Only http and https URLs are allowed')
    if not hostname:
        raise UnsafeURLError('URL is missing a host')
    if parsed.username or parsed.password:
        raise UnsafeURLError('URLs with embedded credentials are not allowed')
    _resolve_public_ips(hostname)
    return parsed


def fetch_image(url, user_agent, max_bytes=MAX_IMAGE_BYTES, max_redirects=MAX_REDIRECTS):
    """Download an image from a public URL.

    Returns ``(image_bytes, mime_type)``. Raises ``UnsafeURLError``,
    ``ImageTooLargeError`` or ``requests.RequestException``.
    """
    headers = {'User-Agent': user_agent}

    for _ in range(max_redirects + 1):
        validate_public_url(url)

        response = requests.get(
            url,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=False,
            stream=True,
        )
        try:
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get('Location')
                if not location:
                    raise UnsafeURLError('Redirect response had no Location header')
                url = urljoin(url, location)
                continue

            response.raise_for_status()

            declared_length = response.headers.get('Content-Length', '')
            if declared_length.isdigit() and int(declared_length) > max_bytes:
                raise ImageTooLargeError('Image is too large')

            content_type = response.headers.get('Content-Type', '')
            content_type = content_type.split(';')[0].strip().lower()
            if not content_type.startswith('image/'):
                raise UnsafeURLError('URL did not return an image')

            data = bytearray()
            for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ImageTooLargeError('Image is too large')

            return bytes(data), content_type
        finally:
            response.close()

    raise UnsafeURLError(f'Too many redirects (max {max_redirects})')
