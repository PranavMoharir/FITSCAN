"""The skills taxonomy and the alias → canonical-name lookup (LLD §6.8).

`taxonomy.json` lists each canonical skill with its aliases and a category. Every alias is
compiled into ONE regular expression, longest alias first, so a single pass over a text finds
multi-word aliases and prefers "machine learning" over "machine". Matches respect word
boundaries and keep symbols, so "java" is not found inside "javascript", and "c++", "c#",
".net" and "node.js" stay intact.

The same normalizer serves job descriptions, resumes (later) and search filters.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TAXONOMY_FILE = Path(__file__).with_name("taxonomy.json")

# Characters that may belong to a skill token besides letters and digits ("c++", "c#", "node.js").
_TOKEN_CHARS = "a-z0-9+#"
# Unicode punctuation replaced one-for-one, so offsets in the normalized text match the original.
_PUNCTUATION = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
                              "—": "-", "−": "-", " ": " "})


def normalize_text(text: str) -> str:
    """Lower-case and standardize punctuation without changing the length of the text."""
    lowered = "".join(ch.lower() if len(ch.lower()) == 1 else ch for ch in text)
    return lowered.translate(_PUNCTUATION)


@dataclass(frozen=True)
class SkillMatch:
    canonical: str
    start: int
    end: int


class Taxonomy:
    """The canonical skills, their categories and the compiled alias pattern."""

    def __init__(self, data: dict[str, dict]):
        self.categories: dict[str, str | None] = {}
        self.alias_to_canonical: dict[str, str] = {}
        for canonical, entry in data.items():
            self.categories[canonical] = entry.get("category")
            for alias in [canonical, *entry.get("aliases", [])]:
                key = normalize_text(alias).strip()
                existing = self.alias_to_canonical.get(key)
                if existing is not None and existing != canonical:
                    raise ValueError(f"alias {alias!r} is used by both {existing} and {canonical}")
                self.alias_to_canonical[key] = canonical

        aliases = sorted(self.alias_to_canonical, key=len, reverse=True)  # longest first
        alternation = "|".join(re.escape(alias).replace(r"\ ", r"[\s\-]+") for alias in aliases)
        # Not preceded by a token character or a dot; not followed by a token character or ".x".
        self._pattern = re.compile(rf"(?<![{_TOKEN_CHARS}.])(?:{alternation})(?![{_TOKEN_CHARS}]|\.[a-z0-9])")

    @property
    def canonical_names(self) -> list[str]:
        return sorted(self.categories)

    def find(self, text: str) -> list[SkillMatch]:
        """Every alias occurrence in the text, left to right, without overlaps."""
        normalized = normalize_text(text)
        matches = []
        for m in self._pattern.finditer(normalized):
            alias = re.sub(r"[\s\-]+", " ", m.group(0))
            canonical = self.alias_to_canonical.get(alias) or self.alias_to_canonical.get(m.group(0))
            if canonical:
                matches.append(SkillMatch(canonical, m.start(), m.end()))
        return matches

    def canonical(self, term: str) -> str | None:
        """Map one term (for example a search filter "js") to its canonical name, or None."""
        key = re.sub(r"\s+", " ", normalize_text(term).strip())
        return self.alias_to_canonical.get(key)


@lru_cache
def get_taxonomy() -> Taxonomy:
    return Taxonomy(json.loads(TAXONOMY_FILE.read_text(encoding="utf-8")))
