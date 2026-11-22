"""The extractor plug-in contract (LLD §5.16, ADR-011).

An extractor turns one page's HTML into raw jobs and links. It never fetches pages and never
touches the database; the crawler does both. Adding a website means adding one file in
`app/extractors/` with a subclass of `BaseExtractor`; the registry finds it automatically.
"""

import re
from dataclasses import dataclass, field
from typing import ClassVar, Literal
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag


@dataclass
class RawJob:
    """Loose job fields exactly as a site shows them; the crawler normalizes and validates them."""

    title: str | None = None
    company: str | None = None
    location: str | None = None
    job_type: str | None = None           # e.g. "Full-time"
    salary_text: str | None = None        # e.g. "₹9,00,000 – ₹14,00,000 per year"
    salary_min: float | None = None       # when the site gives numbers (e.g. JSON-LD)
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    posted_date: str | None = None        # e.g. "2021-04-08" or "3 days ago"
    description: str | None = None        # plain text (one block per line) or HTML
    min_experience_years: float | None = None
    apply_url: str | None = None          # absolute or relative to the page
    is_remote: bool | None = None
    required_skills: list[str] | None = None      # structured skill lists, when the site has them
    nice_to_have_skills: list[str] | None = None


@dataclass
class ExtractionResult:
    jobs: list[RawJob] = field(default_factory=list)
    links: list[str] = field(default_factory=list)


class BaseExtractor:
    """Subclass this in `app/extractors/<site>.py` and set `name`, `label` and `domains`.

    `demo = True` marks a demo site with invented jobs (the mock site, Fake Python Jobs): its
    jobs are labelled demo everywhere and never shown as real openings. A job counts as demo
    exactly when its `source` is the name of a demo extractor; the crawler takes jobs from a
    demo extractor's hosts only through a demo extractor, so this stays true.
    """

    name: ClassVar[str] = ""                     # stored as jobs.source
    label: ClassVar[str] = ""                    # shown in the UI, e.g. "Greenhouse job board"
    description: ClassVar[str] = ""              # one sentence for the list of sources
    demo: ClassVar[bool] = False                 # True: invented jobs on a demo site, never real openings
    domains: ClassVar[tuple[str, ...]] = ()      # hosts this extractor handles
    formats: ClassVar[tuple[Literal["html", "json"], ...]] = ("html",)  # what `parse` reads
    render_mode: ClassVar[Literal["static", "browser"]] = "static"
    ready_selector: ClassVar[str | None] = None  # CSS selector the browser waits for
    # How the crawl form builds a seed URL: a template with one {key} (e.g. a board token), or an example URL.
    seed_template: ClassVar[str | None] = None
    seed_key_label: ClassVar[str | None] = None  # what {key} is, e.g. "Board token"
    example_seed: ClassVar[str | None] = None

    def handles_host(self, url: str) -> bool:
        """True if the URL's host is one of `domains` (or a subdomain), whatever the path."""
        host = (urlsplit(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in self.domains)

    def matches(self, url: str) -> bool:
        return self.handles_host(url)

    def needs_browser(self, url: str, static_html: str) -> bool:
        return False

    def parse(self, url: str, html: str) -> ExtractionResult:
        raise NotImplementedError


# --- Small parsing helpers shared by extractors --------------------------------------------------

_BLOCK_TAGS = ["p", "div", "section", "article", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
               "tr", "table", "dl", "dt", "dd", "header", "footer", "blockquote", "pre"]


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")  # tolerant of malformed HTML


def block_text(element: Tag | BeautifulSoup | None) -> str | None:
    """Readable text with one line per block element; list items keep a "- " bullet."""
    if element is None:
        return None
    element = BeautifulSoup(str(element), "html.parser")  # work on a copy
    for tag in element.find_all(["script", "style", "noscript"]):
        tag.decompose()
    for br in element.find_all("br"):
        br.replace_with("\n")
    for tag in element.find_all(_BLOCK_TAGS):
        tag.insert_before("\n- " if tag.name == "li" else "\n")
        tag.insert_after("\n")
    lines = (re.sub(r"\s+", " ", line).strip() for line in element.get_text().split("\n"))
    text = "\n".join(line for line in lines if line and line != "-")
    return text or None


def text_of(element: Tag | None) -> str | None:
    """The element's text on one line, or None."""
    if element is None:
        return None
    text = re.sub(r"\s+", " ", element.get_text(" ")).strip()
    return text or None


def all_links(soup: BeautifulSoup) -> list[str]:
    return [a["href"] for a in soup.find_all("a", href=True)]
