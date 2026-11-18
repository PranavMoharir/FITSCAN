"""URL normalization and the domain allow-list (LLD §5.11, §5.12).

Every URL is normalized before it is compared or queued, so the same page is fetched only once:
1. relative links are resolved against the page URL;
2. scheme and host are lower-cased; default ports (:80, :443) are removed;
3. the fragment (#section) is removed;
4. tracking parameters (utm_*, gclid, fbclid) are removed and the rest are sorted;
5. an empty path becomes "/" (other trailing slashes are kept);
6. only http and https are accepted (mailto:, javascript:, tel: ... give None).

URLs with a user name or password in them are refused, so credentials never reach logs.
"""

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}
TRACKING_PARAMETERS = {"gclid", "fbclid"}


def normalize_url(url: str, base: str | None = None) -> str | None:
    """The normalized absolute URL, or None if it is not a usable http(s) URL."""
    if not url or not url.strip():
        return None
    try:
        absolute = urljoin(base, url.strip()) if base else url.strip()
        parts = urlsplit(absolute)
        port = parts.port
    except ValueError:
        return None  # e.g. an invalid port number
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in DEFAULT_PORTS or not host or parts.username or parts.password:
        return None
    if ":" in host:
        host = f"[{host}]"  # IPv6 literal
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    )
    return urlunsplit((scheme, netloc, parts.path or "/", urlencode(query), ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_allowed_host(host: str, allowed_domains: list[str]) -> bool:
    """True if the host is an allowed domain or a subdomain of one."""
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in allowed_domains)
