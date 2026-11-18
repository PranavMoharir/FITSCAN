"""Headless Chromium (Playwright) for pages that need JavaScript (LLD §5.16, ADR-011).

Used only when an extractor asks for it. The page URL has already passed the fetcher's
allow-list, SSRF and robots.txt checks; inside the browser, every sub-request is checked again
against the allow-list and the SSRF guard, and images, fonts and media are skipped for speed.

Playwright is imported only when the first page is rendered, so the API and the unit tests do
not need it. The worker image installs it with Chromium.
"""

from app.crawler.ssrf import BlockedHostError, UnresolvableHostError, check_host
from app.crawler.urls import host_of, is_allowed_host

SKIPPED_RESOURCES = {"image", "font", "media"}


class RenderError(Exception):
    pass


class BrowserRenderer:
    def __init__(self, *, allowed_domains: list[str], private_allowlist: list[str], timeout_seconds: float, user_agent: str):
        self.allowed_domains = allowed_domains
        self.private_allowlist = private_allowlist
        self.timeout_ms = timeout_seconds * 1000
        self.user_agent = user_agent
        self._playwright = None
        self._browser = None
        self._context = None

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(user_agent=self.user_agent, java_script_enabled=True)
        self._context.route("**/*", self._filter_request)

    def _filter_request(self, route) -> None:
        request = route.request
        if request.resource_type in SKIPPED_RESOURCES:
            return route.abort()
        if request.url.startswith(("data:", "blob:")):
            return route.continue_()
        host = host_of(request.url)
        try:
            if not is_allowed_host(host, self.allowed_domains):
                return route.abort()
            check_host(host, self.private_allowlist)
        except (BlockedHostError, UnresolvableHostError):
            return route.abort()
        return route.continue_()

    def render(self, url: str, ready_selector: str | None = None) -> str:
        """The page's HTML after its scripts have run."""
        try:
            if self._context is None:
                self._start()
            page = self._context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                if ready_selector:
                    page.wait_for_selector(ready_selector, timeout=self.timeout_ms)
                else:
                    page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
                return page.content()
            finally:
                page.close()
        except Exception as exc:  # Playwright raises its own error types; all mean "did not render"
            raise RenderError(f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}") from exc

    def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    closer.close()
                except Exception:
                    pass
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = self._browser = self._context = None
