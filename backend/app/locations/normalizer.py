"""Find a known city in any text and return its canonical name (LLD §6.6; prepared for LLD §7).

`cities.json` maps each canonical name to its other spellings, for example
"Bengaluru": ["Bangalore"]. The same function serves both sides of a comparison:

    normalize_city("Bangalore, Karnataka, India")   -> "Bengaluru"   (a job location)
    normalize_city("Bengaluru | +91 98765 43210")   -> "Bengaluru"   (a resume header line)

so a candidate in "Bengaluru" and a job in "Bangalore" have the same city. Matching is
case-insensitive and whole-word, the longest spelling wins ("Navi Mumbai" before "Mumbai"), and
text inside email addresses and URLs is ignored. A city that is not in the list gives None.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CITIES_FILE = Path(__file__).with_name("cities.json")
_EMAIL = re.compile(r"[\w.+%'-]+@[\w-]+(?:\.[\w-]+)*")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github)\.com/\S*", re.I)


@dataclass(frozen=True)
class CityList:
    canonical: dict[str, str]  # lower-case spelling -> canonical name
    pattern: re.Pattern

    def find(self, text: str | None) -> str | None:
        """The canonical name of the first known city in the text, or None."""
        if not text:
            return None
        match = self.pattern.search(_URL.sub(" ", _EMAIL.sub(" ", text)).lower())
        return self.canonical[" ".join(match.group(1).split())] if match else None


@lru_cache
def load_cities(path: Path = CITIES_FILE) -> CityList:
    data = json.loads(path.read_text(encoding="utf-8"))
    canonical = {}
    for name, spellings in data.items():
        if name.startswith("_"):
            continue  # "_comment"
        for spelling in [name, *spellings]:
            canonical[" ".join(spelling.lower().split())] = name
    longest_first = sorted(canonical, key=len, reverse=True)
    alternatives = "|".join(re.escape(s).replace(r"\ ", r"\s+") for s in longest_first)
    return CityList(canonical, re.compile(rf"(?<!\w)({alternatives})(?!\w)"))


def normalize_city(text: str | None) -> str | None:
    """Canonical city name found in a candidate's or a job's location text, or None."""
    return load_cities().find(text)
