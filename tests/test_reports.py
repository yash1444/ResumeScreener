"""HTML reports: one file per processed resume, an index, escaping, and content for eligible and rejected candidates."""
from html.parser import HTMLParser
from pathlib import Path

import samples as S
from resume_screener.config import Settings
from resume_screener.html_report import band, report_filename, write_reports
from resume_screener.pipeline import run_pipeline


class _Check(HTMLParser):
    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.scripts = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts += 1
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()


def _run(tmp_path: Path):
    src = tmp_path / "in"
    src.mkdir()
    (src / "strong.txt").write_text(S.STRONG)
    (src / "js_only.txt").write_text(S.JS_ONLY)
    (src / "thin.txt").write_text(S.THIN_WRAPPER)
    out = run_pipeline(src, Settings(openai_api_key=None, github_token=None), analyzer=None)
    return out, write_reports(out, tmp_path / "out")


def test_one_report_per_resume_plus_index(tmp_path):
    out, folder = _run(tmp_path)
    names = {p.name for p in folder.glob("*.html")}
    expected = {report_filename(r) for r in out["ranked_candidates"] + out["rejected_candidates"]}
    assert names == expected | {"index.html"} and len(names) == 4


def test_reports_are_well_formed_self_contained_and_script_free(tmp_path):
    _, folder = _run(tmp_path)
    for page in folder.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        chk = _Check()
        chk.feed(text)
        assert not chk.errors and not chk.stack, (page.name, chk.errors, chk.stack)
        assert chk.scripts == 0 and "http://" not in text.replace("http://www.w3.org", "")  # no scripts, no external assets


def test_eligible_and_rejected_reports_have_the_expected_sections(tmp_path):
    out, folder = _run(tmp_path)
    top = out["ranked_candidates"][0]
    page = (folder / report_filename(top)).read_text(encoding="utf-8")
    for needle in ("Score breakdown", "Strengths", "Skills matched", "Eligibility check", "GitHub activity", "Claims vs. proof",
                   "Evidence log", "Suggested next step", f"Rank #{top['rank']} of 2", str(top["total_score"])):
        assert needle in page, needle
    rej = (folder / report_filename(out["rejected_candidates"][0])).read_text(encoding="utf-8")
    assert "Rejected" in rej and "Why this resume was rejected" in rej and "No evidence of Python stack" in rej
    assert "Score breakdown" not in rej


def test_dynamic_text_is_escaped(tmp_path):
    out, _ = _run(tmp_path)
    r = dict(out["ranked_candidates"][0], candidate_name="<script>alert(1)</script> & Co", project_summary="<img src=x onerror=alert(1)>")
    from resume_screener.html_report import cohort_stats, render_candidate

    page = render_candidate(r, 1, cohort_stats(out["ranked_candidates"]), "now")
    assert "<script>alert" not in page and "<img src=x" not in page and "&lt;script&gt;" in page


def test_bands():
    assert band(85)[1] == "excellent" and band(70)[1] == "strong" and band(55)[1] == "moderate" and band(10)[1] == "weak"
