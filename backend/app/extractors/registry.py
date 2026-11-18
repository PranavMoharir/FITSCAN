"""Finds every extractor plug-in and picks the right one for a URL (LLD §5.16).

Every module in `app/extractors/` is imported, and each `BaseExtractor` subclass with a `name`
is registered, so adding a site needs no change here. Selection order:
1. the extractor named in the crawl request;
2. the first registered extractor whose `matches(url)` is true (alphabetical by name);
3. the generic schema.org JobPosting fallback.
"""

import importlib
import pkgutil
from functools import lru_cache

import app.extractors as package
from app.extractors.base import BaseExtractor

FALLBACK_NAME = "generic"
_NOT_PLUGINS = {"base", "registry"}


class ExtractorRegistry:
    def __init__(self, extractors: list[BaseExtractor]):
        by_name = {e.name: e for e in extractors}
        if FALLBACK_NAME not in by_name:
            raise ValueError("the generic fallback extractor is missing")
        self.fallback = by_name[FALLBACK_NAME]
        self.site_extractors = [by_name[n] for n in sorted(by_name) if n != FALLBACK_NAME]
        self._by_name = by_name

    @property
    def names(self) -> list[str]:
        return sorted(self._by_name)

    def get(self, name: str) -> BaseExtractor:
        return self._by_name[name]

    def select(self, url: str, forced_name: str | None = None) -> BaseExtractor:
        if forced_name:
            return self._by_name[forced_name]
        for extractor in self.site_extractors:
            if extractor.matches(url):
                return extractor
        return self.fallback


def discover() -> list[BaseExtractor]:
    """Import every plug-in module and instantiate each extractor class it defines."""
    found: dict[str, BaseExtractor] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _NOT_PLUGINS:
            continue
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        for value in vars(module).values():
            if (isinstance(value, type) and issubclass(value, BaseExtractor) and value is not BaseExtractor
                    and value.__module__ == module.__name__ and value.name):
                if value.name in found:
                    raise ValueError(f"two extractors are named {value.name!r}")
                found[value.name] = value()
    return list(found.values())


@lru_cache
def get_registry() -> ExtractorRegistry:
    return ExtractorRegistry(discover())
