"""Industry classification (LLD §5.18): labelled examples from every industry, unknown and tied jobs,
the points rule, the explanations, the rules file checks, and the new non-IT skills.

Industries never change skills or scores: they are a label for browsing and filtering.
"""

import copy
import json

import pytest

from app.industries import INDUSTRIES
from app.industries.classifier import MIN_POINTS, OTHER, RULES_FILE, Rules, classify, get_rules, industry_label
from app.models import Job
from app.skills.extractor import extract_job_skills, extract_skills

# (title, description, skills, expected industry): at least two examples per industry, most of them non-IT.
LABELLED = [
    ("Senior Python Developer", "Build REST APIs and review code.", ["Python", "Django", "PostgreSQL"], "software_it"),
    ("IT Support Specialist", "Keep laptops and accounts running for 300 staff.", ["Linux"], "software_it"),
    ("Data Scientist", "Train predictive models on large datasets.", ["Python", "scikit-learn", "Pandas"], "ai_data"),
    ("Business Intelligence Analyst", "Build dashboards for sales leaders.", ["Power BI", "SQL"], "ai_data"),
    ("Senior Financial Analyst", "Monthly reporting for our banking partners.", ["Financial Modeling", "GAAP"],
     "finance_banking"),
    ("Accounts Payable Accountant", "Process invoices and reconcile ledgers.", ["Accounting"], "finance_banking"),
    ("Loan Officer", "Assess lending applications.", [], "finance_banking"),
    ("Growth Marketing Manager", "Run campaigns across search and social media.", ["SEO", "Google Ads"], "marketing"),
    ("Copywriter", "Write web pages and brand stories.", ["Copywriting"], "marketing"),
    ("Account Executive", "Close deals and exceed your quarterly quota.", ["Salesforce", "CRM"], "sales_business"),
    ("Customer Success Manager", "Own renewals for 40 customer accounts.", [], "sales_business"),
    ("HR Generalist", "Payroll, onboarding of new employees and employee relations.", ["Payroll", "HRIS"],
     "human_resources"),
    ("Technical Recruiter", "Run full-cycle recruiting for engineering roles.", ["Talent Acquisition"], "human_resources"),
    ("Senior Product Designer", "Own the design system and prototypes.", ["Figma", "User Research"], "design"),
    ("Graphic Designer", "Create campaign visuals.", ["Adobe Photoshop", "Adobe Illustrator"], "design"),
    ("Supply Chain Planner", "Plan inventory with our suppliers.", ["Supply Chain Management", "SAP"],
     "operations_supply_chain"),
    ("Warehouse Associate", "Pick and pack orders in our fulfillment center.", [], "operations_supply_chain"),
    ("Registered Nurse, ICU", "Provide patient care in a 400-bed hospital.", ["BLS", "ACLS", "Patient Care"],
     "healthcare"),
    ("Staff Pharmacist", "Dispense medication and counsel patients.", ["Medication Administration"], "healthcare"),
    ("Physiotherapist", "Plan treatment for patients after surgery.", [], "healthcare"),
    ("Mathematics Teacher", "Teach students in grades 9 to 12.", ["Lesson Planning", "Classroom Management"],
     "education"),
    ("University Lecturer in Economics", "Lectures and seminars for undergraduate students.", [], "education"),
    ("Mechanical Design Engineer", "Design machinery for our manufacturing plants.", ["SolidWorks", "AutoCAD"],
     "engineering"),
    ("Civil Engineer", "Structural checks for bridges.", ["AutoCAD"], "engineering"),
    ("Corporate Paralegal", "Support our attorneys with litigation files.", ["Legal Research", "Contract Drafting"],
     "legal"),
    ("Legal Counsel", "Advise on contracts and regulatory compliance.", ["Regulatory Compliance"], "legal"),
]


@pytest.mark.parametrize(("title", "description", "skills", "expected"), LABELLED, ids=[row[0] for row in LABELLED])
def test_labelled_examples(title, description, skills, expected):
    assert classify(title, description, skills).industry == expected


def test_every_industry_has_labelled_examples():
    assert {row[3] for row in LABELLED} == set(INDUSTRIES) - {OTHER}
    assert sum(row[3] != "software_it" for row in LABELLED) >= 20  # mostly non-IT


@pytest.mark.parametrize(("title", "description", "skills"), [
    ("Barista", "Make coffee for our guests.", []),
    ("Product Manager", "Own the roadmap.", []),
    ("Coordinator", "Coordinate projects.", ["Excel", "Agile", "Scrum", "Jira"]),  # skills that point nowhere
    (None, None, []),
    ("", "", []),
])
def test_jobs_without_evidence_are_other(title, description, skills):
    result = classify(title, description, skills)
    assert result.industry == OTHER
    assert result.reasons() == ["No industry terms in the title, skills or description."]


def test_weak_evidence_is_not_forced_into_an_industry():
    result = classify("Coordinator", "Help our sales team with spreadsheets.", ["Python"])
    assert result.industry == OTHER  # 1 point for Software & IT, 1 for Sales & Business: below 3
    assert result.reasons()[0].startswith("Too little evidence: the strongest industry")


def test_a_tie_is_not_forced_into_an_industry():
    result = classify("Teacher and Nurse", None, [])  # 3 points each
    assert result.industry == OTHER
    assert result.reasons() == ["Education and Healthcare are equally likely (3 points each)."]


def test_the_title_outweighs_the_description():
    result = classify("Registered Nurse", "Join our software team's clinic: APIs, code reviews and cloud infrastructure.", [])
    # Four software terms in the description count at most 3 points; the title alone is worth 3, and "clinic" adds 1.
    assert result.points["software_it"] == 3 and result.points["healthcare"] == 3 + 1
    assert result.industry == "healthcare"


def test_description_alone_needs_three_different_terms():
    assert classify("Associate", "patients and patients and patients", []).industry == OTHER  # one term, counted once
    assert classify("Associate", "Patients, clinical rounds and the hospital ward.", []).industry == "healthcare"


def test_skills_alone_need_three_skills_of_one_industry():
    assert classify("Associate", None, ["SEO", "Google Ads"]).industry == OTHER
    assert classify("Associate", None, ["SEO", "Google Ads", "Copywriting"]).industry == "marketing"


def test_each_kind_of_evidence_is_capped():
    result = classify("Nurse Clinician Midwife Paramedic", None, [])
    assert result.points["healthcare"] == 6  # four title terms, at most 6 points
    many = ["Python", "Java", "Go", "Rust", "Ruby", "PHP"]
    assert classify("Associate", None, many).points["software_it"] == 4


def test_terms_are_whole_words_and_longest_first():
    assert classify("Data Engineer", None, []).signals[0].term == "data engineer"  # not "engineer" anywhere
    assert classify("Tax Advisor", None, []).industry == "finance_banking"
    assert classify("Taxi Driver", None, []).industry == OTHER  # "tax" is not inside "taxi"
    assert classify("Front-end Developer", None, []).industry == "software_it"


def test_reasons_name_the_evidence_with_its_points():
    result = classify("Registered Nurse", "Patient care on the ward of a hospital.", ["BLS", "Patient Care"])
    assert result.reasons() == ['Title: "nurse" (+3)', "Skills: BLS, Patient Care (+2)",
                                'Description: "patient", "hospital" (+2)']
    assert result.reasons("education") == ["No current evidence for Education."]


def test_classification_does_not_change_skill_extraction():
    description = "Requirements:\n- Patient care\n- BLS\nNice to have:\n- ACLS"
    before = extract_job_skills(description)
    classify("Registered Nurse", description, before.required + before.nice_to_have)
    after = extract_job_skills(description)
    assert (after.required, after.nice_to_have) == (before.required, before.nice_to_have) == (["BLS", "Patient Care"], ["ACLS"])


# --- The rules file -------------------------------------------------------------------------------


def test_codes_labels_and_the_database_constraint_agree():
    rules = get_rules()
    assert rules.codes == INDUSTRIES
    assert industry_label(OTHER) == "Other / Unclassified" and industry_label("ai_data") == "AI & Data Science"
    check = next(c for c in Job.__table__.constraints if getattr(c, "name", "") == "ck_jobs_industry")
    assert all(f"'{code}'" in str(check.sqltext) for code in INDUSTRIES)
    assert MIN_POINTS == 3


def _rules_data():
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def test_a_term_may_belong_to_one_industry_only():
    data = copy.deepcopy(_rules_data())
    data["industries"]["legal"]["title"].append("nurse")
    with pytest.raises(ValueError, match="belongs to both"):
        Rules(data)


def test_skill_exceptions_must_name_real_skills_and_industries():
    data = copy.deepcopy(_rules_data())
    data["skills"]["Basket Weaving"] = "design"
    with pytest.raises(ValueError, match="not a skill of the taxonomy"):
        Rules(data)
    data = copy.deepcopy(_rules_data())
    data["skills"]["Excel"] = "other"
    with pytest.raises(ValueError, match="cannot point"):
        Rules(data)


def test_the_industry_list_is_fixed():
    data = copy.deepcopy(_rules_data())
    del data["industries"]["legal"]
    with pytest.raises(ValueError, match="must list exactly"):
        Rules(data)


# --- New non-IT skills in the taxonomy --------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [
    ("BLS and ACLS certified; EHR experience; patient care", ["ACLS", "BLS", "Electronic Health Records", "Patient Care"]),
    ("Financial modelling, US GAAP and IFRS reporting", ["Financial Modeling", "GAAP", "IFRS"]),
    ("SEO, Google Ads and GA4 dashboards", ["Google Ads", "Google Analytics", "SEO"]),
    ("Salesforce, B2B sales and lead generation", ["B2B Sales", "Lead Generation", "Salesforce"]),
    ("Payroll, HRIS and employee relations", ["Employee Relations", "HRIS", "Payroll"]),
    ("Wireframes, user research and UI design in Adobe Photoshop", ["Adobe Photoshop", "UI Design", "User Research",
                                                                     "Wireframing"]),
    ("Supply chain, inventory control and procurement in SAP", ["Inventory Management", "Procurement", "SAP",
                                                                "Supply Chain Management"]),
    ("Lesson plans, classroom management and special education", ["Classroom Management", "Lesson Planning",
                                                                  "Special Education"]),
    ("AutoCAD, SolidWorks and finite element analysis", ["AutoCAD", "Finite Element Analysis", "SolidWorks"]),
    ("Contract review, legal research and litigation", ["Contract Drafting", "Legal Research", "Litigation"]),
])
def test_non_it_skills_and_aliases(text, expected):
    assert extract_skills(text) == expected


@pytest.mark.parametrize("text", [
    "Salary: CAD 90,000 a year",                     # Canadian dollars, not computer-aided design
    "Contoso Holdings PLC is hiring",                # a UK company suffix, not PLC programming
    "Experience with AML patients in oncology",      # acute myeloid leukaemia, not anti-money laundering
    "Maple sap season starts in March",              # lower-case "sap" outside a skill list
    "Our recruitment process takes two weeks",       # no "Recruiting" skill from boilerplate
])
def test_ambiguous_words_are_not_skills(text):
    assert extract_skills(text) == []


def test_sap_counts_in_capitals_or_in_a_skill_list():
    assert extract_skills("We run SAP for finance") == ["SAP"]
    assert extract_skills("Skills: excel, sap, procurement") == ["Excel", "Procurement", "SAP"]
