"""Skill extraction and normalization (LLD §6.8-6.9, §9.7)."""

import pytest

from app.skills.extractor import extract_job_skills, extract_skills
from app.skills.normalizer import Taxonomy, get_taxonomy


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("JS and ReactJS", ["JavaScript", "React"]),                         # the brief's examples
        ("Java Script, react.js and ECMAScript", ["JavaScript", "React"]),
        ("machine learning engineer", ["Machine Learning"]),                 # longest match first
        ("javascript developer", ["JavaScript"]),                            # "java" is not inside "javascript"
        ("Java and JavaScript", ["Java", "JavaScript"]),
        ("C++, C# and .NET", [".NET", "C#", "C++"]),                         # symbols stay intact
        ("node.js, Vue.js, Next.js", ["Next.js", "Node.js", "Vue.js"]),
        ("Postgres, k8s, CI/CD and scikit-learn", ["CI/CD", "Kubernetes", "PostgreSQL", "scikit-learn"]),
        ("Python.", ["Python"]),                                             # sentence-final full stop
        ("pythonic code", []),                                               # word boundaries
    ],
)
def test_aliases_map_to_canonical_names(text, expected):
    assert extract_skills(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Skills: Python, Go, R, C", ["C", "Go", "Python", "R"]),     # a list item of its own
        ("We use Go and REST APIs", ["Go", "REST"]),                  # case-sensitive forms
        ("Golang services", ["Go"]),
        ("Go to the office. Spring is here.", []),                    # ordinary words
        ("let's go; get some rest", []),
        ("Candidates who excel at Excel", ["Excel"]),
    ],
)
def test_ambiguous_words_need_a_skill_context(text, expected):
    assert extract_skills(text) == expected


@pytest.mark.parametrize("text", ["R&D team", "R & D", "a go-to-market plan", "C-level clients", "the rest of the team",
                                  "C-suite"])
def test_known_false_phrases_are_rejected(text):
    assert extract_skills(text) == []


def test_requirements_and_nice_to_have_example_from_the_lld():
    skills = extract_job_skills("Requirements: Python, FastAPI, PostgreSQL. Docker is a plus.\nNice to have: Redis, Kubernetes")
    assert skills.required == ["FastAPI", "PostgreSQL", "Python"]
    assert skills.nice_to_have == ["Docker", "Kubernetes", "Redis"]


def test_without_headings_every_skill_is_required():
    assert extract_job_skills("We build Django apps on AWS.").required == ["AWS", "Django"]


def test_a_skill_in_both_groups_is_required():
    skills = extract_job_skills("Requirements\n- Python\nPreferred\n- Python\n- AWS")
    assert (skills.required, skills.nice_to_have) == (["Python"], ["AWS"])


@pytest.mark.parametrize("qualifier", ["is a plus", "preferred", "nice to have", "bonus", "ideally"])
def test_inline_qualifiers_override_the_heading(qualifier):
    skills = extract_job_skills(f"Must have:\n- Python\n- Terraform {qualifier}")
    assert (skills.required, skills.nice_to_have) == (["Python"], ["Terraform"])


def test_other_headings_end_the_nice_to_have_section():
    skills = extract_job_skills("Nice to have:\n- Redis\nResponsibilities:\n- Build services in Python")
    assert (skills.required, skills.nice_to_have) == (["Python"], ["Redis"])


def test_structured_lists_come_first_and_unknown_terms_are_reported():
    skills = extract_job_skills("Description mentions Java", ["python 3", "Looker"], ["k8s"])
    assert (skills.required, skills.nice_to_have, skills.unmatched) == (["Python"], ["Kubernetes"], ["looker"])


def test_unmatched_terms_come_from_skill_lists():
    assert extract_job_skills("Requirements: Python, dbt, Looker Studio").unmatched == ["dbt", "looker studio"]


def test_ambiguous_aliases_are_not_reported_as_unmatched():
    # The line from the mock site's "Go Backend Engineer". Go is saved as required, so the crawl
    # summary must not also list "go" as a term missing from the taxonomy.
    skills = extract_job_skills("Requirements\n- Go, PostgreSQL and Kafka\n- Experience with dbt, Airflow")
    assert skills.required == ["Airflow", "Go", "Kafka", "PostgreSQL"]
    assert skills.unmatched == ["experience with dbt"]


def test_search_terms_use_the_same_normalizer():
    taxonomy = get_taxonomy()
    assert [taxonomy.canonical(t) for t in ["js", " ReactJS ", "Postgres", "golang", "unknown-thing"]] == [
        "JavaScript", "React", "PostgreSQL", "Go", None]


def test_taxonomy_is_consistent():
    taxonomy = get_taxonomy()
    assert len(taxonomy.canonical_names) >= 50
    assert all(taxonomy.categories[name] for name in taxonomy.canonical_names)
    with pytest.raises(ValueError, match="used by both"):
        Taxonomy({"A": {"aliases": ["x"]}, "B": {"aliases": ["x"]}})


# --- Labelled examples: precision and recall (LLD §6.9) ---------------------------------------------

LABELLED = [
    ("Requirements\n- 3+ years with Python\n- FastAPI or Django, and PostgreSQL\n- Docker is a plus\nNice to have\n- Redis",
     {"Python", "FastAPI", "Django", "PostgreSQL"}, {"Docker", "Redis"}),
    ("What you need: React, TypeScript and CSS; comfortable with Git.\nBonus: Figma",
     {"React", "TypeScript", "CSS", "Git"}, {"Figma"}),
    ("Our R&D team needs SQL and Power BI. Tableau preferred.", {"SQL", "Power BI"}, {"Tableau"}),
    ("Qualifications:\nGo, Kafka, PostgreSQL. Designing REST APIs.\nPlus: Kubernetes",
     {"Go", "Kafka", "PostgreSQL", "REST"}, {"Kubernetes"}),
]


def test_precision_and_recall_on_labelled_examples():
    true_positive = extracted = labelled = 0
    for text, required, nice in LABELLED:
        skills = extract_job_skills(text)
        found = {(s, "required") for s in skills.required} | {(s, "nice") for s in skills.nice_to_have}
        expected = {(s, "required") for s in required} | {(s, "nice") for s in nice}
        true_positive += len(found & expected)
        extracted += len(found)
        labelled += len(expected)
    precision, recall = true_positive / extracted, true_positive / labelled
    print(f"skill extraction on labelled examples: precision {precision:.2f}, recall {recall:.2f}")
    assert precision == 1.0 and recall == 1.0  # measured values on these fixtures, recorded in the README


def test_ambiguous_words_count_inside_a_requirements_section():
    skills = extract_job_skills("Requirements: Go\n- Spring and REST\nNice to have: Swift\nAbout us:\nGo to our office.")
    assert (skills.required, skills.nice_to_have) == (["Go", "REST", "Spring"], ["Swift"])
    assert extract_job_skills("Requirements:\n- you will go to client sites").required == []  # lower-case prose
