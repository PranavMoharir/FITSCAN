"""What the API shows of background-job logs, parameters and failure reasons.

The worker stores its log lines as it wrote them: they are the record of what happened, and the crawler,
the resume pipeline and their tests rely on them. Before any of it reaches a browser (GET
/background-jobs/{id} and /background-jobs/{id}/logs), this module removes what someone following a
job's progress does not need and an outsider must not see:

- credentials, fragments and the values of secret-looking query parameters in URLs;
- internal host names (single-label names such as `mock-site` or `db`, the crawler's private-host
  allow-list, internal suffixes such as `.local`) and IP addresses;
- file-system paths, stack traces and anything after the first line of a message;
- e-mail addresses, phone numbers and `password=...`-style secrets;
- full upload and candidate IDs (shortened to the 8 characters the log messages already use), and
  storage file names.

Progress stays visible: levels, timestamps, counts, public page URLs, retry attempts, robots.txt
results and failure summaries. Nothing here changes what is stored or how a job runs.
"""

import ipaddress
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.config import get_settings

REDACTED = "[redacted]"
INTERNAL_HOST = "[internal host]"
IP_ADDRESS = "[IP address]"
PATH = "[path]"
EMAIL = "[email]"
NUMBER = "[number]"
DETAILS_REMOVED = "[details removed]"

SHORT_ID_LENGTH = 8
SHORT_ID_KEYS = frozenset({"upload_id", "candidate_id"})
DROPPED_KEYS = frozenset({"stored_file", "stored_path", "source_file", "file_name", "filename", "resume_text", "path"})
INTERNAL_SUFFIXES = ("localhost", "local", "internal", "lan", "home.arpa", "corp", "intranet", "invalid", "test")

_SECRET_QUERY_KEY = re.compile(r"token|secret|passw|pwd|key|auth|sig|session|credential|jwt|ticket|code", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_URL_TRAILING = ".,;:!?)]}'\""
_TRACEBACK = re.compile(r"Traceback \(most recent call last\)|\bFile \"[^\"]+\", line \d+")
_POSIX_PATH = re.compile(r"(?<![\w.:/\]-])/(?:data|app|tmp|home|usr|var|etc|opt|root|srv|mnt|proc|ms-playwright|uploads)"
                         r"(?:/[^\s\"',;)]*)?")
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\[^\s\"',;)]*")
# "Authorization: Bearer <token>": the whole value goes, not just its first word.
_AUTHORIZATION = re.compile(r"\b(authorization)(\s*[=:]\s*)([^\n,;]+)", re.IGNORECASE)
_KEY_VALUE_SECRET = re.compile(r"\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token)(\s*[=:]\s*)(\S+)",
                               re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+(?!\[redacted\])\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])\[?(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}\]?(?![\w:])")
_PHONE = re.compile(r"(?<![\w.+-])\+?\d(?:[ ().-]?\d){9,14}(?![\w.-])")
_HOSTNAME = r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
# Host names in the crawler's own messages ("Loaded robots.txt for <host>", "<host> resolves to a private
# or reserved address", "could not resolve <host>", "All of <host> is treated as disallowed").
_HOST_POSITIONS = (
    re.compile(rf"(robots\.txt for )({_HOSTNAME})"),
    re.compile(rf"(All of )({_HOSTNAME})(?= is treated as disallowed)"),
    re.compile(rf"()({_HOSTNAME})(?= resolves to a private or reserved address)"),
    re.compile(rf"(could not resolve )({_HOSTNAME})"),
)
_PRIVATE_RESOLVING = re.compile(rf"({_HOSTNAME}) resolves to a private or reserved address")
# Only the list in "Crawl started: <url> (max_depth 2, max_pages 10, allowed domains a, b)".
_ALLOWED_DOMAINS = re.compile(r"(, allowed domains )([^)\n]+)(?=\))")
_INTERNAL_NAME = re.compile(rf"\b{_HOSTNAME}\.(?:{'|'.join(re.escape(s) for s in INTERNAL_SUFFIXES)})\b", re.IGNORECASE)


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text.strip("[]"))
    except ValueError:
        return False
    return True


def _allow_listed_hosts() -> set[str]:
    return {host.lower() for host in get_settings().crawler_private_host_allowlist} | {"localhost"}


def is_internal_host(host: str, also_internal: frozenset[str] = frozenset()) -> bool:
    """A name that is meaningful only inside a private network, or an IP address. `also_internal`: names
    the same message says resolve to a private address."""
    name = host.strip().strip("[]").rstrip(".").lower()
    if not name:
        return False
    if _is_ip(name) or "." not in name or name in _allow_listed_hosts() or name in also_internal:
        return True
    return any(name == suffix or name.endswith("." + suffix) for suffix in INTERNAL_SUFFIXES)


def redact_host(host: str, also_internal: frozenset[str] = frozenset()) -> str:
    if _is_ip(host):
        return IP_ADDRESS
    return INTERNAL_HOST if is_internal_host(host, also_internal) else host


def redact_url(url: str, also_internal: frozenset[str] = frozenset()) -> str:
    """The URL without credentials or fragment, with secret query values and internal hosts replaced."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return REDACTED
    host = parts.hostname
    if parts.scheme.lower() not in ("http", "https") or not host:
        return REDACTED
    shown = redact_host(host, also_internal)
    netloc = shown if shown != host else (f"{host}:{port}" if port else host)
    query = urlencode([(key, REDACTED if _SECRET_QUERY_KEY.search(key) else value)
                       for key, value in parse_qsl(parts.query, keep_blank_values=True)], safe="[]")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, query, ""))


def _redact_plain(text: str, also_internal: frozenset[str]) -> str:
    """Rules for text outside URLs."""
    text = _POSIX_PATH.sub(PATH, text)
    text = _WINDOWS_PATH.sub(PATH, text)
    text = _AUTHORIZATION.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _KEY_VALUE_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    text = _EMAIL.sub(EMAIL, text)
    text = _IPV4.sub(lambda m: IP_ADDRESS if _is_ip(m.group(0)) else m.group(0), text)
    text = _IPV6.sub(lambda m: IP_ADDRESS if _is_ip(m.group(0)) else m.group(0), text)
    for pattern in _HOST_POSITIONS:
        text = pattern.sub(lambda m: m.group(1) + redact_host(m.group(2), also_internal), text)
    text = _ALLOWED_DOMAINS.sub(
        lambda m: m.group(1) + ", ".join(redact_host(h.strip(), also_internal) for h in m.group(2).split(",")), text)
    text = _INTERNAL_NAME.sub(INTERNAL_HOST, text)
    allow_listed = sorted(_allow_listed_hosts() | also_internal, key=len, reverse=True)
    if allow_listed:
        text = re.sub(rf"(?<![\w.-])(?:{'|'.join(map(re.escape, allow_listed))})(?![\w-])", INTERNAL_HOST, text,
                      flags=re.IGNORECASE)
    return _PHONE.sub(NUMBER, text)


def redact_text(text: str | None) -> str | None:
    """A log message or failure reason as the API shows it."""
    if not text:
        return text
    cut = _TRACEBACK.search(text)
    first_line, _, rest = text.partition("\n")
    if cut and cut.start() < len(first_line):
        text = text[:cut.start()].rstrip() + " " + DETAILS_REMOVED
    elif cut or rest.strip():
        text = first_line.rstrip() + " " + DETAILS_REMOVED
    # A host the message itself says resolves to a private address is internal everywhere in it.
    also_internal = frozenset(m.group(1).lower() for m in _PRIVATE_RESOLVING.finditer(text))
    pieces, last = [], 0
    for match in _URL.finditer(text):
        url = match.group(0).rstrip(_URL_TRAILING)
        pieces.append(_redact_plain(text[last:match.start()], also_internal))
        pieces.append(redact_url(url, also_internal))
        last = match.start() + len(url)
    pieces.append(_redact_plain(text[last:], also_internal))
    return "".join(pieces)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return redact_context(value)
    return value


def redact_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """A log line's structured context: counts stay, identifiers are shortened, text is redacted."""
    if not isinstance(context, dict):
        return context
    shown: dict[str, Any] = {}
    for key, value in context.items():
        if key in DROPPED_KEYS:
            continue
        if key in SHORT_ID_KEYS and isinstance(value, str):
            shown[key] = value[:SHORT_ID_LENGTH]
        elif key == "url" and isinstance(value, str):
            shown[key] = redact_url(value)
        elif key == "host" and isinstance(value, str):
            shown[key] = redact_host(value)
        else:
            shown[key] = _redact_value(value)
    return shown


def redact_params(job_type: str, params: dict[str, Any] | None) -> dict[str, Any] | None:
    """A job's parameters as the API shows them."""
    if not isinstance(params, dict):
        return params
    if job_type == "resume":
        files = params.get("files")
        if not isinstance(files, list):
            return {}
        # Each file: the short upload reference the log lines use, and its size. Never a name or storage path.
        return {"files": [{"upload_id": str(item.get("upload_id", ""))[:SHORT_ID_LENGTH] or None,
                           "size_bytes": item.get("size_bytes")}
                          for item in files if isinstance(item, dict)]}
    shown = dict(params)
    if job_type == "crawl":
        if isinstance(shown.get("seed_url"), str):
            shown["seed_url"] = redact_url(shown["seed_url"])
        if isinstance(shown.get("allowed_domains"), list):
            shown["allowed_domains"] = [redact_host(str(host)) for host in shown["allowed_domains"]]
    return shown
