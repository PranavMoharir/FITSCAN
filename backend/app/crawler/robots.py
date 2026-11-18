"""robots.txt rules, fetched once per host per crawl and cached (LLD §5.13, ADR-009).

| robots.txt response | Treatment                                                          |
| 200                 | Use the rules; a longer Crawl-delay replaces the configured delay  |
| 404 or other 4xx    | No rules: everything is allowed                                    |
| 5xx or unreachable  | The whole host is disallowed for this crawl (the polite choice)    |
"""

from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

# Returns (status code, body), or raises an exception when robots.txt cannot be reached.
RobotsFetch = Callable[[str], tuple[int, str]]


class RobotsPolicy:
    def __init__(self, rules: RobotFileParser | None, allow_all: bool = False, reason: str | None = None):
        self._rules = rules
        self._allow_all = allow_all
        self.reason = reason  # why the whole host is disallowed, if it is

    def allowed(self, user_agent: str, url: str) -> bool:
        if self._allow_all:
            return True
        if self._rules is None:
            return False
        return self._rules.can_fetch(user_agent, url)

    def crawl_delay(self, user_agent: str) -> float | None:
        if self._rules is None:
            return None
        delay = self._rules.crawl_delay(user_agent)
        return float(delay) if delay is not None else None


class RobotsCache:
    def __init__(self, fetch: RobotsFetch, user_agent: str, on_new_host: Callable[[str, RobotsPolicy], None] | None = None):
        self._fetch = fetch
        self._user_agent = user_agent
        self._on_new_host = on_new_host
        self._policies: dict[str, RobotsPolicy] = {}

    @staticmethod
    def robots_url(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    def policy_for(self, url: str) -> RobotsPolicy:
        key = self.robots_url(url)
        if key not in self._policies:
            self._policies[key] = self._load(key)
            if self._on_new_host:
                self._on_new_host(key, self._policies[key])
        return self._policies[key]

    def allowed(self, url: str) -> bool:
        return self.policy_for(url).allowed(self._user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        return self.policy_for(url).crawl_delay(self._user_agent)

    def _load(self, robots_url: str) -> RobotsPolicy:
        try:
            status, body = self._fetch(robots_url)
        except Exception:
            return RobotsPolicy(None, reason="robots.txt could not be reached")
        if status == 200:
            rules = RobotFileParser()
            rules.parse(body.splitlines())
            return RobotsPolicy(rules)
        if 400 <= status < 500:
            return RobotsPolicy(None, allow_all=True)
        return RobotsPolicy(None, reason=f"robots.txt returned HTTP {status}")
