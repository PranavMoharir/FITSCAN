"""City normalization shared by candidates and jobs (LLD §6.6; prepared for the location fit of LLD §7).

The matching engine is not built yet. These tests only show that one function turns a resume's
city and a job's location into the same canonical name.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from app.locations.normalizer import load_cities, normalize_city


@pytest.mark.parametrize(("text", "city"), [
    ("Bangalore, India", "Bengaluru"), ("Lives in New Delhi", "Delhi"), ("Navi Mumbai, Maharashtra", "Navi Mumbai"),
    ("Gurgaon | ravi@example.com", "Gurugram"), ("PUNE", "Pune"), ("Remote", None), (None, None), ("", None),
    ("pune.dev@example.com", None),            # a city inside an email address does not count
    ("https://www.pune-jobs.example/", None),  # nor inside a URL
])
def test_cities_are_matched_against_the_list(text, city):
    assert normalize_city(text) == city


@pytest.mark.parametrize(("job_location", "city"), [
    ("Pune, India", "Pune"),                      # as the mock site writes it (LLD §7 example)
    ("Pune, Maharashtra, India", "Pune"),
    ("Bangalore, Karnataka, India", "Bengaluru"),
    ("Bengaluru (Hybrid)", "Bengaluru"),
    ("Hybrid - Gurgaon", "Gurugram"),
    ("Remote", None),                             # remote jobs are handled by the matching rule, not here
    ("Davidville, AP", None),                     # not a listed city: the matching phase decides the fallback
])
def test_job_locations_use_the_same_normalization(job_location, city):
    assert normalize_city(job_location) == city


def test_a_candidate_in_bengaluru_and_a_job_in_bangalore_have_the_same_city():
    candidate_city = normalize_city("Bengaluru | asha@example.com | +91 98765 43210")
    job_city = normalize_city("Bangalore, Karnataka, India")
    assert candidate_city == job_city == "Bengaluru"


def test_every_spelling_maps_to_one_canonical_name():
    cities = load_cities()
    assert cities.canonical["bangalore"] == cities.canonical["bengaluru"] == "Bengaluru"
    assert all(cities.canonical[name.lower()] == name for name in set(cities.canonical.values()))  # names map to themselves
    assert len(set(cities.canonical.values())) >= 45


def test_the_module_needs_no_worker_libraries():
    """The API image has no PDF, OCR or browser libraries, and must still be able to use this module."""
    code = ("import sys; import app.locations.normalizer; "
            "print(sorted(m for m in ('pymupdf', 'pdfplumber', 'pytesseract', 'PIL', 'playwright') if m in sys.modules))")
    backend = Path(__file__).resolve().parents[2]
    out = subprocess.run([sys.executable, "-c", code], cwd=backend, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
