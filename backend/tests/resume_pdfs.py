"""Synthetic resume PDFs, generated with PyMuPDF while the tests run (LLD §9.6).

Every person here is invented: emails use example.com and phone numbers are fictional. No real
resume, including the developer's, is ever used.

Layouts: one column, two columns (with a full-width header), skills in a ruled table, scanned
(the one-column page as an image, with no text layer), password-protected, and corrupt bytes.

To write them to a folder for manual uploads:  python -m tests.resume_pdfs <folder>
"""

import sys
from dataclasses import dataclass, field, replace
from html import escape
from pathlib import Path

import pymupdf

A4 = pymupdf.paper_rect("a4")  # 595 x 842 points
CSS = """
* { font-family: sans-serif; }
p { font-size: 10pt; margin: 0 0 3pt 0; }
h1 { font-size: 22pt; font-weight: bold; margin: 0 0 2pt 0; }
h2 { font-size: 13pt; font-weight: bold; margin: 10pt 0 3pt 0; }
.title { font-size: 12pt; }
"""


@dataclass
class Job:
    title: str
    company: str
    dates: str
    bullets: list[str] = field(default_factory=list)


@dataclass
class Person:
    name: str = "Asha Verma"
    title: str = "Senior Backend Engineer"
    email: str = "asha.verma@example.com"
    phone: str = "+91 98765 43210"
    location: str = "Pune, India"
    summary: str = ("Backend engineer with 6+ years of experience building reliable APIs and data pipelines "
                    "for analytics products.")
    jobs: list[Job] = field(default_factory=lambda: [
        Job("Senior Backend Engineer", "Acme Analytics", "Jan 2021 – Present",
            ["Built REST APIs with FastAPI and PostgreSQL", "Moved batch jobs to Celery and Redis"]),
        Job("Software Engineer", "Globex Systems", "Jun 2017 – Dec 2021",
            ["Wrote services in Go and Python", "Ran deployments on Docker and Kubernetes"]),
    ])
    education: list[str] = field(default_factory=lambda: [
        "B.Tech in Computer Engineering, Savitribai Phule Pune University, 2013 – 2017"])
    skills: str = "Python, Go, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, C++, Node.js"


def _contact(person: Person) -> str:
    return " | ".join(escape(part) for part in (person.location, person.email, person.phone) if part)


def _experience_html(person: Person) -> str:
    html = "<h2>Experience</h2>"
    for job in person.jobs:
        html += f"<p><b>{escape(job.title)}, {escape(job.company)}</b> ({escape(job.dates)})</p>"
        html += "".join(f"<p>- {escape(bullet)}</p>" for bullet in job.bullets)
    return html


def _sections_html(person: Person, *, skills: bool = True) -> str:
    html = f"<h2>Summary</h2><p>{escape(person.summary)}</p>" if person.summary else ""
    html += _experience_html(person)
    html += "<h2>Education</h2>" + "".join(f"<p>{escape(line)}</p>" for line in person.education)
    if skills:
        html += f"<h2>Skills</h2><p>{escape(person.skills)}</p>"
    return html


def _header_html(person: Person, *, contact: bool = True) -> str:
    html = f"<h1>{escape(person.name)}</h1>" if person.name else ""
    html += f'<p class="title">{escape(person.title)}</p>' if person.title else ""
    return html + (f"<p>{_contact(person)}</p>" if contact else "")


def _document_bytes(document: pymupdf.Document) -> bytes:
    data = document.tobytes(garbage=3, deflate=True)
    document.close()
    return data


def one_column(person: Person | None = None) -> bytes:
    person = person or Person()
    document = pymupdf.open()
    page = document.new_page(width=A4.width, height=A4.height)
    page.insert_htmlbox(pymupdf.Rect(50, 45, 545, 800), _header_html(person) + _sections_html(person), css=CSS)
    return _document_bytes(document)


def two_column(person: Person | None = None) -> bytes:
    """Full-width header; left column: contact, skills, education; right column: summary, experience."""
    person = person or Person()
    document = pymupdf.open()
    page = document.new_page(width=A4.width, height=A4.height)
    page.insert_htmlbox(pymupdf.Rect(40, 40, 555, 110), _header_html(person, contact=False), css=CSS)
    left = ("<h2>Contact</h2>" + "".join(f"<p>{escape(p)}</p>" for p in (person.location, person.email, person.phone))
            + f"<h2>Skills</h2>" + "".join(f"<p>{escape(s.strip())}</p>" for s in person.skills.split(","))
            + "<h2>Education</h2>" + "".join(f"<p>{escape(line)}</p>" for line in person.education))
    right = (f"<h2>Summary</h2><p>{escape(person.summary)}</p>" if person.summary else "") + _experience_html(person)
    page.insert_htmlbox(pymupdf.Rect(40, 120, 205, 800), left, css=CSS)
    page.insert_htmlbox(pymupdf.Rect(235, 120, 555, 800), right, css=CSS)
    return _document_bytes(document)


TABLE_ROWS = [("Languages", "Python, C++, C#"), ("Frameworks", ".NET, Node.js, React"),
              ("Data", "R"), ("Cloud", "AWS, Docker")]


def table(person: Person | None = None, rows: list[tuple[str, str]] = TABLE_ROWS) -> bytes:
    """A one-column resume whose skills are a ruled table (cell borders drawn as lines)."""
    person = person or Person()
    document = pymupdf.open()
    page = document.new_page(width=A4.width, height=A4.height)
    page.insert_htmlbox(pymupdf.Rect(50, 45, 545, 560), _header_html(person) + _sections_html(person, skills=False),
                        css=CSS)
    page.insert_htmlbox(pymupdf.Rect(50, 570, 545, 600), "<h2>Skills</h2>", css=CSS)
    top, height, columns = 600, 22, (50, 190, 545)
    for index, (label, value) in enumerate(rows):
        y = top + index * height
        for x0, x1, text in ((columns[0], columns[1], label), (columns[1], columns[2], value)):
            page.draw_rect(pymupdf.Rect(x0, y, x1, y + height), color=(0, 0, 0), width=0.7)
            page.insert_text((x0 + 5, y + 15), text, fontname="helv", fontsize=10)
    return _document_bytes(document)


def scanned(person: Person | None = None, dpi: int = 200) -> bytes:
    """The one-column resume as a picture: no text layer, so only OCR can read it."""
    source = pymupdf.open(stream=one_column(person), filetype="pdf")
    pixmap = source[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    document = pymupdf.open()
    page = document.new_page(width=A4.width, height=A4.height)
    page.insert_image(page.rect, pixmap=pixmap)
    source.close()
    return _document_bytes(document)


def blank_scan() -> bytes:
    """An image-only page with nothing on it: OCR finds no text."""
    document = pymupdf.open()
    page = document.new_page(width=A4.width, height=A4.height)
    pixmap = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 400, 560), False)
    pixmap.clear_with(255)
    page.insert_image(page.rect, pixmap=pixmap)
    return _document_bytes(document)


def encrypted(person: Person | None = None) -> bytes:
    document = pymupdf.open(stream=one_column(person), filetype="pdf")
    data = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user-secret", owner_pw="owner-secret")
    document.close()
    return data


def corrupt() -> bytes:
    """Starts with the PDF signature (so the API accepts it) but is not a PDF inside."""
    return b"%PDF-1.7\n" + bytes(range(256)) * 40


def pages(count: int, person: Person | None = None) -> bytes:
    """A resume with `count` pages (for the page limit)."""
    document = pymupdf.open(stream=one_column(person), filetype="pdf")
    for _ in range(count - 1):
        document.new_page(width=A4.width, height=A4.height).insert_text((50, 80), "Additional page", fontsize=10)
    return _document_bytes(document)


PEOPLE = {
    "asha": Person(),
    "rahul": Person(name="Rahul Mehta", title="Data Analyst", email="rahul.mehta@example.com",
                    phone="+91 91234 56789", location="Bangalore, India",
                    summary="Data analyst who turns product data into dashboards and forecasts for business teams.",
                    jobs=[Job("Data Analyst", "Initech", "Mar 2020 – Present", ["Built dashboards in Power BI"]),
                          Job("Junior Analyst", "Umbrella Retail", "Jul 2018 – Jun 2020", ["Wrote SQL reports"])],
                    education=["B.Sc in Statistics, University of Mumbai, 2015 – 2018"],
                    skills="SQL, Python, Pandas, Excel, Power BI, R"),
    "meera": Person(name="Meera Iyer", title="Frontend Developer", email="meera.iyer@example.com",
                    phone="+91 99887 76655", location="Chennai",
                    summary="Frontend developer focused on accessible, fast web interfaces.",
                    jobs=[Job("Frontend Developer", "Hooli", "Aug 2022 – Present", ["Built React and TypeScript apps"])],
                    education=["B.E. in Information Technology, Anna University, 2018 – 2022"],
                    skills="JavaScript, TypeScript, React, HTML, CSS, Node.js"),
}


def write_samples(folder: Path) -> list[Path]:
    """Write one file per layout, for trying the upload by hand (python -m tests.resume_pdfs <folder>)."""
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "cv_01_one_column.pdf": one_column(PEOPLE["asha"]),
        "cv_02_two_column.pdf": two_column(PEOPLE["rahul"]),
        "cv_03_table.pdf": table(PEOPLE["meera"]),
        "cv_04_scanned.pdf": scanned(replace(PEOPLE["asha"], name="Kiran Rao", email="kiran.rao@example.com")),
        "cv_05_encrypted.pdf": encrypted(),
        "cv_06_corrupt.pdf": corrupt(),
    }
    paths = []
    for name, data in files.items():
        (folder / name).write_bytes(data)
        paths.append(folder / name)
    return paths


if __name__ == "__main__":
    for written in write_samples(Path(sys.argv[1] if len(sys.argv) > 1 else "sample-resumes")):
        print(written)
