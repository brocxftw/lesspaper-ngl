"""Validation and classification of AI provider base URLs."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from lesspaper_ngl.core.exceptions import ValidationError

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


@dataclass(frozen=True, slots=True)
class ValidatedProviderURL:
    url: str
    hostname: str
    is_local: bool
    scheme: str
    port: int | None


def _is_private_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _hostname_is_local(hostname: str) -> bool:
    lowered = hostname.lower().rstrip(".")
    if lowered in _LOCAL_HOSTNAMES:
        return True
    if lowered.endswith(".local"):
        return True

    try:
        infos = socket.getaddrinfo(lowered, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    if not infos:
        return False

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        try:
            addresses.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue

    if not addresses:
        return False

    return all(_is_private_ip(address) for address in addresses)


def validate_provider_base_url(raw_url: str) -> ValidatedProviderURL:
    """Validate an AI provider base URL and classify it as local or remote."""
    url = raw_url.strip()
    if not url:
        raise ValidationError("Provider base URL is required.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Provider base URL must use http or https.")

    if not parsed.netloc:
        raise ValidationError("Provider base URL must include a host.")

    if parsed.username or parsed.password:
        raise ValidationError("Credentials must not be embedded in the provider base URL.")

    hostname = parsed.hostname
    if not hostname:
        raise ValidationError("Provider base URL must include a valid host.")

    normalized = url.rstrip("/")
    is_local = _hostname_is_local(hostname)

    return ValidatedProviderURL(
        url=normalized,
        hostname=hostname,
        is_local=is_local,
        scheme=parsed.scheme,
        port=parsed.port,
    )
