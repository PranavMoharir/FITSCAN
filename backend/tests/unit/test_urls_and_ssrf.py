"""URL normalization, the domain allow-list (LLD §5.11-5.12) and the SSRF guard (ADR-012)."""

import pytest

from app.crawler.ssrf import BlockedHostError, UnresolvableHostError, check_host, is_public_address
from app.crawler.urls import host_of, is_allowed_host, normalize_url


@pytest.mark.parametrize(
    ("url", "base", "expected"),
    [
        ("HTTPS://Jobs.Example.com:443/list?utm_source=x&b=2&a=1#top", None, "https://jobs.example.com/list?a=1&b=2"),
        ("http://jobs.example.com:80/a", None, "http://jobs.example.com/a"),
        ("http://jobs.example.com:8080/a", None, "http://jobs.example.com:8080/a"),
        ("https://jobs.example.com", None, "https://jobs.example.com/"),
        ("https://jobs.example.com/list/", None, "https://jobs.example.com/list/"),  # trailing slash kept
        ("/jobs/1.html", "https://jobs.example.com/list/", "https://jobs.example.com/jobs/1.html"),
        ("2.html", "https://jobs.example.com/list/1.html", "https://jobs.example.com/list/2.html"),
        ("../up.html", "https://jobs.example.com/a/b/c.html", "https://jobs.example.com/a/up.html"),
        ("?page=2", "https://jobs.example.com/list", "https://jobs.example.com/list?page=2"),
        ("https://jobs.example.com/x?gclid=1&fbclid=2&utm_medium=m&id=7", None, "https://jobs.example.com/x?id=7"),
        ("https://jobs.example.com/x?b=&a=1", None, "https://jobs.example.com/x?a=1&b="),
        ("#section", "https://jobs.example.com/page", "https://jobs.example.com/page"),
    ],
)
def test_normalize_url(url, base, expected):
    assert normalize_url(url, base=base) == expected


@pytest.mark.parametrize(
    "url",
    ["mailto:jobs@example.com", "javascript:void(0)", "tel:+911234567890", "ftp://example.com/file",
     "https://user:secret@jobs.example.com/", "https://jobs.example.com:99999/", "", "   "],
)
def test_unusable_urls_are_rejected(url):
    assert normalize_url(url, base="https://jobs.example.com/") is None


def test_same_page_written_differently_normalizes_to_one_url():
    variants = ["https://Jobs.example.com/a?y=2&x=1", "https://jobs.example.com:443/a?x=1&y=2#top",
                "https://jobs.example.com/a?x=1&utm_source=mail&y=2"]
    assert len({normalize_url(v) for v in variants}) == 1


@pytest.mark.parametrize(
    ("host", "allowed"),
    [("jobs.example.com", True), ("careers.jobs.example.com", True), ("JOBS.example.com", True),
     ("example.com", False), ("evil-jobs.example.com", False), ("jobs.example.com.evil.net", False)],
)
def test_allow_list_accepts_the_domain_and_its_subdomains(host, allowed):
    assert is_allowed_host(host, ["jobs.example.com"]) is allowed


def test_host_of():
    assert host_of("https://Jobs.Example.com:8443/x") == "jobs.example.com"


@pytest.mark.parametrize(
    ("address", "public"),
    [("93.184.216.34", True), ("8.8.8.8", True), ("2001:4860:4860::8888", True),
     ("10.1.2.3", False), ("172.16.0.1", False), ("192.168.0.10", False), ("127.0.0.1", False),
     ("169.254.169.254", False), ("0.0.0.0", False), ("224.0.0.1", False), ("240.0.0.1", False),
     ("100.64.0.1", False), ("::1", False), ("fe80::1", False), ("fc00::1", False), ("ff02::1", False),
     ("::ffff:127.0.0.1", False), ("::ffff:10.0.0.1", False)],
)
def test_public_and_private_addresses(address, public):
    assert is_public_address(address) is public


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.5", "[::1]", "internal.jobs.example.com",
                                  "metadata.example.com", "mixed.example.com"])
def test_private_hosts_are_blocked(host):
    with pytest.raises(BlockedHostError):
        check_host(host, private_allowlist=[])


def test_public_host_and_allow_listed_private_host_pass():
    check_host("jobs.example.com", private_allowlist=[])
    check_host("internal.jobs.example.com", private_allowlist=["internal.jobs.example.com"])  # explicit exception


def test_unresolvable_host():
    with pytest.raises(UnresolvableHostError):
        check_host("nowhere.invalid", private_allowlist=[])
