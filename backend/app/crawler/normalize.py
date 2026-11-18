"""Turn loose extracted values into clean, typed values (LLD §5.17, step 2).

Each function is small and pure, so it is easy to test and to explain. Values that cannot be
understood become None; the original text is kept where the design says so (salary_text).
"""

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.extractors.base import block_text, soup_of

_TAG = re.compile(r"</?[a-z][a-z0-9]*(\s[^>]*)?>", re.IGNORECASE)


def squash(value: str | None) -> str | None:
    """Collapse whitespace; empty becomes None."""
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or None


def clean_description(value: str | None) -> str | None:
    """Plain text with one block per line; HTML tags and extra whitespace removed."""
    if not value:
        return None
    text = html.unescape(value) if "&lt;" in value else value
    if _TAG.search(text):
        return block_text(soup_of(text))
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line) or None


# --- Dates ----------------------------------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%Y/%m/%d")
_RELATIVE = re.compile(r"(\d+)\+?\s*(minute|hour|day|week|month)s?\s+ago")
_UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}


def parse_posted_date(value: str | None, fetched_at: datetime) -> date | None:
    """An ISO date from "2021-04-08", "8 Apr 2021", "Apr 8, 2021", "3 days ago", "today" ..."""
    text = squash(value)
    if not text:
        return None
    lowered = re.sub(r"^(posted|published|date posted)[:\s]+", "", text.lower()).strip()
    today = fetched_at.date()
    if lowered in {"today", "just now", "new"} or lowered.endswith(("hours ago", "hour ago", "minutes ago")):
        return today
    if lowered == "yesterday":
        return today - timedelta(days=1)
    relative = _RELATIVE.search(lowered)
    if relative:
        return today - timedelta(days=int(relative.group(1)) * _UNIT_DAYS[relative.group(2)])
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", lowered)
    candidates = [iso.group(1)] if iso else []
    candidates.append(lowered.replace(",", ", ").replace("  ", " ").title())
    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
            if 1990 <= parsed.year <= today.year + 1:
                return parsed
    return None


# --- Salary ---------------------------------------------------------------------------------------

_CURRENCIES = ((r"₹|\brs\.?\s*\d|\binr\b|\blpa\b|\blakhs?\b", "INR"), (r"\$|\busd\b", "USD"),
               (r"€|\beur\b", "EUR"), (r"£|\bgbp\b", "GBP"))
_PERIODS = ((r"\bper hour\b|/\s*h(ou)?r\b|\bhourly\b|\ban hour\b", "hour"),
            (r"\bper day\b|/\s*day\b|\bdaily\b|\ba day\b", "day"),
            (r"\bper week\b|/\s*w(ee)?k\b|\bweekly\b|\ba week\b", "week"),
            (r"\bper month\b|/\s*mo(nth)?\b|\bmonthly\b|\ba month\b", "month"),
            (r"\bper (year|annum)\b|/\s*y(ea)?r\b|\bannual(ly)?\b|\byearly\b|\bp\.?a\.?\b|\blpa\b|\ba year\b", "year"))
_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|lpa|lakhs?|l)?(?![a-z])")


@dataclass
class Salary:
    min: Decimal | None = None
    max: Decimal | None = None
    currency: str | None = None
    period: str | None = None


def parse_salary(text: str | None) -> Salary:
    """Numbers from "₹9,00,000 – ₹14,00,000 per year", "$40 - $55 per hour", "12 LPA", "80k" ..."""
    lowered = (squash(text) or "").lower()
    salary = Salary()
    amounts = []
    for number, suffix in _AMOUNT.findall(lowered):
        value = Decimal(number.replace(",", ""))
        if suffix == "k":
            value *= 1000
        elif suffix in {"lpa", "lakh", "lakhs", "l"}:
            value *= 100_000
        amounts.append(value)
    if not amounts:
        return salary
    salary.min, salary.max = min(amounts[:2]), max(amounts[:2])
    salary.currency = next((code for pattern, code in _CURRENCIES if re.search(pattern, lowered)), None)
    salary.period = next((period for pattern, period in _PERIODS if re.search(pattern, lowered)), None)
    return salary


def normalize_period(value: str | None) -> str | None:
    """JSON-LD unitText ("YEAR", "HOUR" ...) to the stored period."""
    lowered = (value or "").strip().lower()
    return lowered if lowered in {"year", "month", "week", "day", "hour"} else None


# --- Job type, remote, experience -----------------------------------------------------------------


def map_job_type(value: str | None) -> str:
    """One of full_time, part_time, contract, internship, temporary, unknown."""
    text = re.sub(r"[\s_\-]+", " ", (value or "").lower())
    if "intern" in text:
        return "internship"
    if "part time" in text:
        return "part_time"
    if "full time" in text or "permanent" in text:
        return "full_time"
    if "contract" in text or "freelance" in text:
        return "contract"
    if "temporary" in text or text.strip() == "temp":
        return "temporary"
    return "unknown"


_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\banywhere\b", re.IGNORECASE)


def detect_remote(*texts: str | None) -> bool:
    return any(_REMOTE.search(t) for t in texts if t)


_EXPERIENCE = re.compile(
    r"(?:at least|minimum(?: of)?|min\.?)?\s*(\d{1,2}(?:\.\d)?)\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?"
    r"(?:years?|yrs?)\b", re.IGNORECASE)


def extract_min_experience(description: str | None) -> Decimal | None:
    """The first "N years ... experience" requirement, e.g. "3+ years of experience" -> 3."""
    for line in (description or "").splitlines():
        if "experience" not in line.lower():
            continue
        match = _EXPERIENCE.search(line)
        if match:
            years = Decimal(match.group(1))
            if 0 <= years <= 50:
                return years
    return None


# --- De-duplication key (LLD §3.6, ADR-020) -------------------------------------------------------


def make_dedup_key(apply_url: str | None, source: str, title: str | None, company: str | None, location: str | None) -> str:
    """The normalized apply URL; otherwise a SHA-256 of source + title + company + location."""
    if apply_url:
        return apply_url
    basis = "|".join((squash(part) or "").lower() for part in (source, title, company, location))
    return "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()
