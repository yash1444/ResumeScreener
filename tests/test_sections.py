"""Section detection fixes: invisible characters, wrapped-line fragments, heading wording, scrambled PDF block order."""
import fitz

from resume_screener.extraction import build_profile, split_sections
from resume_screener.ingestion import read_resume
from resume_screener.models import RawResume

BODY = "Built a multi-agent workflow with LangGraph and tool calling over a retrieval index with embeddings in pgvector."


def keys(text):
    return {k for k, v in split_sections(text).sections.items() if v}


def test_invisible_characters_no_longer_hide_headings(tmp_path):
    path = tmp_path / "r.txt"
    path.write_text(
        f"Jane Doe\nSKILLS​\nPython, FastAPI, Docker\nPROJECTS​\nAgent | Python, LangGraph\n{BODY}\nEDUCATION\nBTech 2024 Some University\n",
        encoding="utf-8",
    )
    raw = read_resume(path)
    assert "​" not in raw.text
    assert {"skills", "projects", "education"} <= keys(raw.text)


def test_wrapped_line_fragments_are_not_headings():
    text = (
        "Experience\nBuilt a chatbot for\nthe\nproject\nfocused on retrieval and embeddings for support teams that saved hours.\n"
        "Designed an offline assistant for textbook\neducational QA\nand deployed it to Android devices with local models.\n"
        "Full stack system for student records and\nacademic information.\nwith REST APIs and a MySQL database.\n"
    )
    found = keys(text)
    assert "projects" not in found and "education" not in found and "experience" in found


def test_real_headings_still_detected_including_lowercase_after_a_finished_line():
    assert {"skills", "projects"} <= keys("Header line here\n\nskills\nPython, SQL\n\nprojects\nBuilt a thing with Python.\n")
    assert keys("Header\nEducation\nB.Tech 2024\n") >= {"education"}


def test_new_heading_wordings_are_recognised():
    for heading, expected in [("Skills Summary", "skills"), ("CORE COMPETENCIES", "skills"), ("PROFILE SUMMARY", "summary"),
                              ("OBJECTIVES", "summary"), ("PROFILE OBJECTIVE", "summary"), ("Certificates & Achievements", "certifications"),
                              ("KEY ACHIEVEMENTS & METRICS", "certifications"), ("OPEN SOURCE", "experience"), ("INVOLVEMENT", "other")]:
        assert expected in keys(f"Name\n{heading}\nsome content that belongs under this heading\n"), heading
    assert "certifications" not in keys("Name\nEDUCATION\nGraduation\nCourse\nCollege\nScore\n")  # 'Course' is a table label


def _scrambled_pdf(path):
    """Headings are written first and the contents afterwards, so the PDF's own text order is scrambled."""
    doc = fitz.open()
    page = doc.new_page()
    for y, t in [(100, "SUMMARY"), (190, "SKILLS"), (280, "PROJECTS")]:
        page.insert_text((50, y), t)
    page.insert_text((50, 60), "Jane Doe  jane@example.com  github.com/janedoe")
    page.insert_text((50, 120), "Backend engineer who ships LLM powered agents and retrieval systems.")
    page.insert_text((50, 210), "Python, FastAPI, LangGraph, PostgreSQL, Docker, Redis, pgvector")
    page.insert_text((50, 300), "Research Agent: " + BODY)
    doc.save(path)


def test_scrambled_pdf_is_read_in_page_order(tmp_path):
    path = tmp_path / "scrambled.pdf"
    _scrambled_pdf(path)
    raw = read_resume(path)
    stream_projects = split_sections(raw.text).sections.get("projects", "")
    assert "Python, FastAPI" in stream_projects  # stream order puts the skills text under PROJECTS: the problem being fixed
    profile = build_profile(raw)
    assert profile.reordered is True
    assert "Python, FastAPI" in profile.sections.sections["skills"]
    assert "LangGraph" in profile.sections.sections["projects"] and "Python, FastAPI" not in profile.sections.sections["projects"]


def test_well_ordered_pdf_keeps_its_own_order(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for t in ["Jane Doe  jane@example.com", "SKILLS", "Python, FastAPI, LangGraph, Docker and PostgreSQL", "PROJECTS", "Agent: " + BODY]:
        page.insert_text((50, y), t)
        y += 40
    doc.save(tmp_path / "ok.pdf")
    profile = build_profile(read_resume(tmp_path / "ok.pdf"))
    assert profile.reordered is False and "skills" in profile.sections.sections
