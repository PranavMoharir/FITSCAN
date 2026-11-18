"""SSRF guard: never fetch loopback, private, link-local, multicast or reserved addresses (ADR-012).

The crawler accepts user-supplied URLs, so without this guard it could be used to reach
internal services (for example the database container or a cloud metadata address).
Hosts listed in CRAWLER_PRIVATE_HOST_ALLOWLIST (for example `mock-site`) are the only exception.
"""

import ipaddress
import socket


class BlockedHostError(Exception):
    """The host resolves to an address the crawler must not contact."""


class UnresolvableHostError(Exception):
    """The host name does not resolve."""


def resolve_host(host: str) -> list[str]:
    """All IP addresses of a host. Tests replace this function, so they never use real DNS."""
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)})
    except (socket.gaierror, UnicodeError) as exc:
        raise UnresolvableHostError(f"could not resolve {host}") from exc


def is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])  # drop an IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # is_global is False for private, loopback, link-local, reserved, unspecified and shared ranges.
    return ip.is_global and not ip.is_multicast


def check_host(host: str, private_allowlist: list[str]) -> None:
    """Raise BlockedHostError unless every address of the host is public (or the host is allow-listed)."""
    host = host.lower().strip("[]")
    if host in {h.lower() for h in private_allowlist}:
        return
    try:
        addresses = [str(ipaddress.ip_address(host))]  # the host is an IP literal
    except ValueError:
        addresses = resolve_host(host)
    blocked = [a for a in addresses if not is_public_address(a)]
    if blocked:
        raise BlockedHostError(f"{host} resolves to a private or reserved address")
