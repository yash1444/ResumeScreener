"""Per-candidate HTML reports (plus an index page), generated from the same data as results.json.

Self-contained files: inline CSS, no JavaScript, no external requests. Light and dark themes, responsive, print-friendly.
Everything dynamic is HTML-escaped. The reports are decision support for a recruiter, not decisions.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

CATEGORIES = [
    ("ai_project_depth", "AI / agentic / RAG project depth", 40, "Real AI systems: agents, retrieval, tools, state, evaluation"),
    ("python_backend", "Python &amp; backend engineering", 30, "Python, FastAPI, async, PostgreSQL, Redis, shown in projects"),
    ("cloud_fullstack", "Cloud / deployment / full stack", 15, "GCP/AWS, Docker, CI/CD, end-to-end systems"),
    ("github", "GitHub activity", 10, "Recent public activity and maintained, relevant repositories"),
    ("engineering_depth", "Engineering depth signals", 5, "Testing, architecture, caching, queues, observability, failure handling"),
]
BORDERLINE_TEXT = {
    "python_only_in_skills_list": "Python appears only in the skills list, with no project or job that uses it.",
    "ai_evidence_is_thin": "AI evidence is thin: two or fewer distinct LLM / retrieval / agent terms inside project entries.",
    "ai_keywords_only_in_skills_or_summary": "AI keywords appear only in the skills list or summary, not inside any project or job.",
}
BANDS = [(80, "Excellent match", "excellent"), (65, "Strong match", "strong"), (50, "Moderate match", "moderate"), (0, "Weak match", "weak")]
NEXT_STEP = {
    "excellent": "Shortlist for interview",
    "strong": "Shortlist for interview",
    "moderate": "Keep in the pool; consider after stronger candidates",
    "weak": "Low priority",
}

CSS = """
:root{--bg:#f5f6fa;--card:#fff;--ink:#1c2233;--muted:#667085;--line:#e4e7ef;--accent:#4f46e5;--accent-soft:#eef0ff;
--good:#12805c;--good-soft:#e3f6ee;--warn:#9a6700;--warn-soft:#fff4d6;--bad:#b42318;--bad-soft:#fde8e6;--info:#175cd3;--info-soft:#e5efff;
--track:#e9ecf5;--shadow:0 1px 2px rgba(16,24,40,.06),0 4px 14px rgba(16,24,40,.05)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1220;--card:#181c2e;--ink:#e8ebf5;--muted:#9aa3bd;--line:#2a3050;
--accent:#8b87ff;--accent-soft:#25285a;--good:#4ade9a;--good-soft:#123a2c;--warn:#f5c451;--warn-soft:#3b2f0e;--bad:#ff8a80;--bad-soft:#47201d;
--info:#7db2ff;--info-soft:#142a52;--track:#262b47;--shadow:0 1px 2px rgba(0,0,0,.4)}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}h1,h2,h3{line-height:1.25;margin:0}
.wrap{max-width:1040px;margin:0 auto;padding:20px 16px 48px}
.top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:14px;font-size:13px;color:var(--muted)}
.hero{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:24px;display:grid;
grid-template-columns:1fr auto;gap:24px;align-items:center}
.hero h1{font-size:28px;letter-spacing:-.01em}
.meta{margin-top:6px;color:var(--muted);display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:999px;font-size:13px;font-weight:600;border:1px solid transparent}
.b-good{background:var(--good-soft);color:var(--good)}.b-warn{background:var(--warn-soft);color:var(--warn)}
.b-bad{background:var(--bad-soft);color:var(--bad)}.b-info{background:var(--info-soft);color:var(--info)}.b-plain{background:var(--accent-soft);color:var(--accent)}
.ring{--p:0;--size:132px;width:var(--size);height:var(--size);border-radius:50%;display:grid;place-items:center;
background:conic-gradient(var(--ringc,var(--accent)) calc(var(--p)*1%),var(--track) 0)}
.ring>div{width:calc(var(--size) - 24px);height:calc(var(--size) - 24px);border-radius:50%;background:var(--card);display:grid;place-items:center;text-align:center}
.ring b{font-size:34px;line-height:1}.ring small{display:block;color:var(--muted);font-size:12px;margin-top:2px}
.verdict{margin-top:16px;border:1px solid var(--line);border-left:5px solid var(--accent);border-radius:12px;padding:14px 16px;background:var(--card);box-shadow:var(--shadow)}
.verdict.excellent,.verdict.strong{border-left-color:var(--good)}.verdict.moderate{border-left-color:var(--warn)}.verdict.weak,.verdict.rejected{border-left-color:var(--bad)}
.verdict .lead{font-weight:700;font-size:16px}.verdict p{margin:6px 0 0;color:var(--muted)}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 4px}
nav.toc a{text-decoration:none;font-size:13px;padding:5px 12px;border-radius:999px;background:var(--card);border:1px solid var(--line);color:var(--ink)}
nav.toc a:hover{border-color:var(--accent);color:var(--accent)}
section{margin-top:22px;scroll-margin-top:12px}
section>h2{font-size:18px;margin-bottom:4px;display:flex;align-items:center;gap:10px}
section>h2 .n{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:8px;background:var(--accent-soft);color:var(--accent);font-size:13px}
.sub{color:var(--muted);font-size:13.5px;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:18px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.grid5{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-top:16px}
.cat{padding:10px 0;border-top:1px solid var(--line)}.cat:first-child{border-top:0;padding-top:0}
.cat .row{display:flex;justify-content:space-between;gap:12px;align-items:baseline}.cat .name{font-weight:600}.cat .pts{font-variant-numeric:tabular-nums;font-weight:700}
.cat .hint{color:var(--muted);font-size:13px}
.bar{position:relative;height:10px;background:var(--track);border-radius:99px;margin:7px 0 4px}
.bar i{display:block;height:100%;border-radius:99px;background:var(--accent)}
.bar u{position:absolute;top:-3px;width:2px;height:16px;background:var(--ink);opacity:.55;border-radius:2px}
.legend{font-size:12.5px;color:var(--muted);margin-top:10px}
ul.clean{margin:0;padding-left:18px}ul.clean li{margin:5px 0}
ul.ticks{list-style:none;margin:0;padding:0}ul.ticks li{padding-left:24px;position:relative;margin:7px 0}
ul.ticks li::before{content:"\\2713";position:absolute;left:0;color:var(--good);font-weight:700}
ul.warns{list-style:none;margin:0;padding:0}ul.warns li{padding-left:24px;position:relative;margin:7px 0}
ul.warns li::before{content:"!";position:absolute;left:2px;top:1px;width:16px;height:16px;border-radius:50%;background:var(--warn-soft);color:var(--warn);font-size:11px;font-weight:700;text-align:center;line-height:16px}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{padding:3px 10px;border-radius:8px;background:var(--accent-soft);color:var(--accent);font-size:13px;font-weight:500}
.chip.ok{background:var(--good-soft);color:var(--good)}.chip.no{background:var(--track);color:var(--muted)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;margin:0}.kv dt{color:var(--muted)}.kv dd{margin:0;font-weight:500}
.stat{text-align:center}.stat b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.stat span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.04em}tr:last-child td{border-bottom:0}
.tw{overflow-x:auto}
details{border:1px solid var(--line);border-radius:12px;background:var(--card);margin:8px 0;padding:0 14px}
details summary{cursor:pointer;padding:11px 0;font-weight:600}details[open] summary{border-bottom:1px solid var(--line);margin-bottom:8px}
details ul{margin:6px 0 12px}
.note{border-radius:12px;padding:12px 14px;background:var(--info-soft);color:var(--info);font-size:13.5px;margin-top:12px}
.note.warn{background:var(--warn-soft);color:var(--warn)}
.quote{font-size:15.5px;border-left:3px solid var(--accent);padding:2px 0 2px 14px;margin:0}
footer{margin-top:34px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:14px}
.idx td a{font-weight:600;text-decoration:none}.idx .num{font-variant-numeric:tabular-nums;text-align:right}
.minibar{display:inline-block;width:70px;height:7px;border-radius:99px;background:var(--track);vertical-align:middle;margin-right:8px;overflow:hidden}
.minibar i{display:block;height:100%;background:var(--accent)}
@media (max-width:760px){.hero{grid-template-columns:1fr;justify-items:start}.grid2,.grid3{grid-template-columns:1fr}.grid5{grid-template-columns:repeat(2,1fr)}.hero h1{font-size:24px}}
@media print{body{background:#fff}.card,.hero,.verdict,details{box-shadow:none}nav.toc,.top a{display:none}details{break-inside:avoid}details>*{display:block}}
"""

e = html.escape


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "candidate"


def report_filename(r: dict) -> str:
    stem = Path(r.get("filename", "resume")).stem
    return f"{stem}_{slug(r.get('candidate_name', ''))}.html"


def band(score: int) -> tuple[str, str]:
    for floor, label, key in BANDS:
        if score >= floor:
            return label, key
    return BANDS[-1][1], BANDS[-1][2]


def _li(items, cls="clean") -> str:
    items = [i for i in items if i]
    return f'<ul class="{cls}">' + "".join(f"<li>{e(str(i))}</li>" for i in items) + "</ul>" if items else '<p class="sub">None recorded.</p>'


def _chips(items, cls="") -> str:
    return '<div class="chips">' + "".join(f'<span class="chip {cls}">{e(str(i))}</span>' for i in items) + "</div>" if items else '<p class="sub">None found.</p>'


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{e(title)}</title><style>{CSS}</style></head><body><div class=\"wrap\">{body}</div></body></html>"
    )


def cohort_stats(ranked: list[dict]) -> dict:
    n = len(ranked)
    if not n:
        return {"n": 0, "mean_total": 0, "mean": {}}
    return {
        "n": n,
        "mean_total": sum(r["total_score"] for r in ranked) / n,
        "mean": {k: sum(r["score_breakdown"][k] for r in ranked) / n for k, *_ in CATEGORIES},
    }


# ----------------------------------------------------------------------------------------------- sections
def _verify_list(r: dict) -> list[str]:
    """What a recruiter may want to confirm, built only from facts in the record."""
    out: list[str] = []
    chk = r.get("eligibility_check") or {}
    if chk.get("needs_human_review"):
        out.append("Confirm basic eligibility first: the LLM second opinion disagrees with the rule-based decision.")
    cv = r.get("claim_verification") or {}
    if cv.get("unverified_techs"):
        out.append("Ask to see the code or discuss how these were used: " + ", ".join(cv["unverified_techs"][:6]) + " (not confirmed in public repos; they may be private).")
    for p in r.get("penalties", []):
        out.append("Probe project depth: " + p)
    for c in (r.get("concerns") or [])[:3]:
        out.append("Concern raised in the review: " + c)
    if not r.get("github"):
        out.append("No GitHub profile in the resume: ask for a code sample or portfolio.")
    elif (r["github"].get("status") not in ("ok", "partial")):
        out.append("GitHub could not be checked (" + str(r["github"].get("status")) + "): look at the profile manually.")
    return out


def _header(r: dict, rank_total: int, status_badges: list[tuple[str, str]], ring_value: int | None, ring_label: str, ringc: str) -> str:
    name = e(r.get("candidate_name", "Unknown"))
    meta = []
    if r.get("email"):
        meta.append(f'<span>&#9993; <a href="mailto:{e(r["email"])}">{e(r["email"])}</a></span>')
    gh = r.get("github") or {}
    if gh.get("username"):
        meta.append(f'<span>GitHub: <a href="https://github.com/{e(gh["username"])}" target="_blank" rel="noopener">{e(gh["username"])}</a></span>')
    meta.append(f'<span>Source file: {e(r.get("filename", ""))}</span>')
    badges = "".join(f'<span class="badge {c}">{e(t)}</span>' for t, c in status_badges)
    ring = ""
    if ring_value is not None:
        ring = f'<div class="ring" style="--p:{ring_value};--ringc:{ringc}"><div><span><b>{ring_value}</b><small>{e(ring_label)}</small></span></div></div>'
    return f'<div class="hero"><div><h1>{name}</h1><div class="meta">{"".join(meta)}</div><div class="badges">{badges}</div></div>{ring}</div>'


def _toc(items: list[tuple[str, str]]) -> str:
    return '<nav class="toc">' + "".join(f'<a href="#{i}">{e(t)}</a>' for i, t in items) + "</nav>"


def _sec(num: int, sid: str, title: str, sub: str, inner: str) -> str:
    return f'<section id="{sid}"><h2><span class="n">{num}</span>{e(title)}</h2><p class="sub">{sub}</p>{inner}</section>'


def _score_section(r: dict, cohort: dict) -> str:
    b, ev = r["score_breakdown"], r.get("evidence", {})
    rows = []
    for key, label, mx, hint in CATEGORIES:
        v = b.get(key, 0)
        avg = cohort["mean"].get(key)
        tick = f'<u style="left:{min(100, avg / mx * 100):.1f}%" title="Average of eligible candidates: {avg:.1f}"></u>' if avg is not None else ""
        why = ev.get(key, [])
        why_html = ""
        if why:
            why_html = "<details><summary>What earned these points</summary>" + _li(why) + "</details>"
        rows.append(
            f'<div class="cat"><div class="row"><span class="name">{label}</span><span class="pts">{v} <span class="hint">/ {mx}</span></span></div>'
            f'<div class="bar"><i style="width:{v / mx * 100:.1f}%"></i>{tick}</div><div class="hint">{hint}</div>{why_html}</div>'
        )
    pen = r.get("penalties") or []
    pen_html = ""
    if pen:
        pen_html = '<div class="note warn"><b>Deductions applied to AI depth</b>' + _li(pen, "clean") + "</div>"
    legend = f'<div class="legend">Dark tick on each bar = average of the {cohort["n"]} eligible candidates. Total {r["total_score"]} vs average {cohort["mean_total"]:.1f}.</div>'
    return f'<div class="card">{"".join(rows)}{pen_html}{legend}</div>'


def _eligibility_section(r: dict) -> str:
    ev = r.get("evidence", {})
    py, ai = ev.get("eligibility_python", []), ev.get("eligibility_ai", [])
    eligible = r.get("eligible")
    none_py = '<span class="sub">No evidence found.</span>'
    none_ai = '<span class="sub">No qualifying AI project found inside a project or job entry.</span>'
    py_cell = _li(py) if py else none_py
    ai_cell = _li(ai) if ai else none_ai
    rows = f"<tr><td><b>Python</b></td><td>{py_cell}</td></tr><tr><td><b>AI / agentic work</b></td><td>{ai_cell}</td></tr>"
    reasons = ""
    if not eligible and r.get("rejection_reasons"):
        reasons = '<div class="note warn"><b>Why this resume was rejected</b>' + _li(r["rejection_reasons"]) + "</div>"
    chk = r.get("eligibility_check")
    chk_html = ""
    if chk:
        why = "".join(f"<li>{e(BORDERLINE_TEXT.get(x, x))}</li>" for x in chk.get("borderline_reasons", []))
        op = chk.get("llm_second_opinion")
        if op:
            verdict = ("agrees with the rules" if chk.get("llm_agrees") else "<b>disagrees with the rules</b>")
            op_html = (
                f'<dl class="kv"><dt>Python genuine?</dt><dd>{"Yes" if op["python_is_genuine"] else "No"}: {e(op.get("python_evidence", ""))}</dd>'
                f'<dt>Built with LLM / agents?</dt><dd>{"Yes" if op["builds_with_llm_or_agents"] else "No"}: {e(op.get("ai_evidence", ""))}</dd>'
                f'<dt>Confidence</dt><dd>{e(op.get("confidence", ""))}</dd><dt>Reasoning</dt><dd>{e(op.get("reasoning", ""))}</dd></dl>'
            )
        else:
            verdict = "was not available"
            op_html = f'<p class="sub">{e(chk.get("second_opinion_error", "No second opinion was obtained."))}</p>'
        cls = "note warn" if chk.get("needs_human_review") else "note"
        chk_html = (
            f'<div class="{cls}"><b>Borderline case: second opinion {verdict}.</b> The rule-based decision '
            f'(<b>{e(chk["rules_decision"])}</b>) is final; the LLM can only flag a case for review.<ul class="clean">{why}</ul></div>'
            f'<div class="card" style="margin-top:12px"><h3 style="margin-bottom:8px">LLM second opinion</h3>{op_html}</div>'
        )
    return (
        '<div class="card"><div class="tw"><table><thead><tr><th style="width:170px">Requirement</th><th>Evidence found in the resume</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></div>{reasons}{chk_html}"
    )


def _github_section(r: dict) -> str:
    g = r.get("github")
    if not g:
        return '<div class="card"><p>No GitHub profile was found in the resume, so nothing was checked. This does not affect eligibility.</p></div>'
    stats = (
        f'<div class="grid3"><div class="card stat"><b>{g.get("maintained_repos", "n/a")}</b><span>repos pushed in the last 12 months</span></div>'
        f'<div class="card stat"><b>{g.get("relevant_repos", "n/a")}</b><span>Python / AI relevant repos</span></div>'
        f'<div class="card stat"><b>{g.get("recent_events") if g.get("recent_events") is not None else "n/a"}</b><span>public events in the last 90 days</span></div></div>'
    )
    detail = (
        f'<div class="card" style="margin-top:14px"><dl class="kv"><dt>Status</dt><dd>{e(str(g.get("status")))}</dd>'
        f'<dt>Activity score</dt><dd>{g.get("activity_score", 0)} / 5</dd><dt>Repository score</dt><dd>{g.get("repo_score", 0)} / 5</dd>'
        f'<dt>Relevant repos</dt><dd>{e(", ".join(g.get("relevant_repo_names", [])) or "none listed")}</dd>'
        f'<dt>Summary</dt><dd>{e(r.get("github_summary", ""))}</dd></dl>'
        + (f'<div class="note warn">{e(g["detail"])}</div>' if g.get("detail") else "")
        + "</div>"
    )
    return stats + detail


def _claims_section(r: dict) -> str:
    cv = r.get("claim_verification")
    if not cv:
        return '<div class="card"><p>Not run: needs a GitHub profile and at least one verifiable technology named in the candidate\'s projects or jobs.</p></div>'
    if cv.get("status") != "checked":
        return f'<div class="card"><p>{e(cv.get("summary", ""))}</p><p class="sub">Status: {e(cv.get("status", ""))}</p></div>'
    verified = cv.get("verified_in", {})
    chips = "".join(
        f'<span class="chip ok" title="{e(verified[t])}">&#10003; {e(t)}</span>' for t in cv.get("verified_techs", [])
    ) + "".join(f'<span class="chip no">? {e(t)}</span>' for t in cv.get("unverified_techs", []))
    repo_rows = "".join(
        f'<tr><td><a href="https://github.com/{e(x["repo"])}" target="_blank" rel="noopener">{e(x["repo"])}</a></td><td>{e(x["source"].replace("_", " "))}</td>'
        f'<td>{"fork (ignored)" if x["is_fork"] else "original"}</td><td>{x["active_span_days"] if x["active_span_days"] is not None else "n/a"} d</td>'
        f'<td>{e(", ".join(x["claimed_techs_found"]) or "none")}</td></tr>' for x in cv.get("repos_checked", [])
    )
    found_rows = "".join(f"<tr><td>{e(t)}</td><td>{e(w)}</td></tr>" for t, w in verified.items())
    bonus = cv.get("score_bonus", 0)
    return (
        f'<div class="card"><div class="row" style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap"><div><b>{cv["claims_verified"]} of {cv["claims_total"]}</b> '
        f'claimed technologies confirmed in public code</div><span class="badge b-{"good" if bonus else "plain"}">Score effect: +{bonus} on AI depth</span></div>'
        f'<div class="chips" style="margin-top:12px">{chips}</div>'
        f'<p class="legend">&#10003; = found in a repo (hover for where) &nbsp; ? = not confirmed. Not confirmed does <b>not</b> mean false.</p></div>'
        f'<details open><summary>Repositories checked</summary><div class="tw"><table><thead><tr><th>Repo</th><th>Why chosen</th><th>Type</th><th>History</th><th>Claims found</th></tr></thead><tbody>{repo_rows}</tbody></table></div></details>'
        + (f'<details><summary>Where each confirmed technology was found</summary><div class="tw"><table><tbody>{found_rows}</tbody></table></div></details>' if found_rows else "")
        + f'<div class="note">{e(cv.get("check_scope", ""))}</div>'
    )


def _evidence_section(r: dict) -> str:
    ev, parts = r.get("evidence", {}), []
    labels = {
        "llm_ai_project_depth": "LLM review: AI project depth", "llm_python_backend": "LLM review: Python &amp; backend",
        "llm_cloud_fullstack": "LLM review: cloud &amp; full stack", "llm_engineering_depth": "LLM review: engineering depth",
    }
    for k, lab in labels.items():
        if ev.get(k):
            parts.append(f"<details><summary>{lab}</summary>{_li(ev[k])}</details>")
    return "".join(parts) or '<div class="card"><p>No LLM evidence recorded (rule-based scoring only).</p></div>'


def _notes_section(r: dict) -> str:
    notes = r.get("notes", [])
    if r.get("eligible"):
        method = f'{r.get("scoring_method") or "n/a"} ("rules+llm" = rule score adjusted by a bounded LLM review)'
    else:
        method = "Rule-based eligibility filter only (rejected resumes are not scored)"
    return (
        f'<div class="card"><dl class="kv"><dt>Scoring method</dt><dd>{e(method)}</dd>'
        f'<dt>Source file</dt><dd>{e(r.get("filename", ""))}</dd></dl>' + (_li(notes) if notes else "") + "</div>"
    )


# ----------------------------------------------------------------------------------------------- pages
def render_candidate(r: dict, rank_total: int, cohort: dict, generated: str) -> str:
    eligible = bool(r.get("eligible"))
    chk = r.get("eligibility_check") or {}
    review = bool(chk.get("needs_human_review"))
    badges: list[tuple[str, str]] = []
    if eligible:
        label, key = band(r["total_score"])
        badges += [("Eligible", "b-good"), (f"Rank #{r['rank']} of {rank_total}", "b-plain"), (label, "b-good" if key in ("excellent", "strong") else "b-warn" if key == "moderate" else "b-bad")]
        ring = (r["total_score"], "score / 100", {"excellent": "var(--good)", "strong": "var(--good)", "moderate": "var(--warn)", "weak": "var(--bad)"}[key])
    else:
        badges += [("Rejected", "b-bad")]
        key, ring = "rejected", (None, "", "var(--bad)")
    if review:
        badges.append(("Needs human review", "b-warn"))
    if r.get("claim_verification", {}) and r["claim_verification"].get("status") == "checked":
        cv = r["claim_verification"]
        badges.append((f"{cv['claims_verified']}/{cv['claims_total']} claims confirmed on GitHub", "b-info"))

    if eligible:
        step = NEXT_STEP[key]
        if review:
            step = "Verify eligibility first, then: " + step.lower()
        verdict = (
            f'<div class="verdict {key}"><div class="lead">Suggested next step: {e(step)}</div>'
            f"<p>{e(r.get('project_summary', ''))}</p>"
            f'<p class="legend">Bands (display only, not part of the rubric): 80+ Excellent, 65-79 Strong, 50-64 Moderate, below 50 Weak. This is decision support, not a decision.</p></div>'
        )
    else:
        verdict = (
            f'<div class="verdict rejected"><div class="lead">Suggested next step: Do not proceed on the stated requirements</div>'
            f"<p>{e('; '.join(r.get('rejection_reasons', [])))}</p>"
            + (f"<p>Best project found: {e(r['project_summary'])}</p>" if r.get("project_summary") else "")
            + (f"<p><b>However:</b> the LLM second opinion suggests this candidate may qualify. A manual look is worthwhile.</p>" if review else "")
            + "</div>"
        )

    toc_items = [("elig", "Eligibility")]
    sections = [_sec(1, "elig", "Eligibility check", "The two hard requirements, decided by rules: genuine Python and real AI / LLM / agentic work.", _eligibility_section(r))]
    n = 2
    if eligible:
        strengths = f'<div class="card"><h3 style="margin-bottom:8px">Strengths</h3>{_li(r.get("strengths", []), "ticks")}</div>'
        concerns = f'<div class="card"><h3 style="margin-bottom:8px">Concerns</h3>{_li(r.get("concerns", []), "warns")}</div>'
        verify = _verify_list(r)
        verify_html = f'<div class="card" style="margin-top:14px"><h3 style="margin-bottom:8px">Worth verifying in an interview</h3>{_li(verify)}</div>' if verify else ""
        sections = [
            _sec(1, "score", "Score breakdown", "Out of 100, using the company rubric. Each bar shows points earned against the maximum.", _score_section(r, cohort)),
            _sec(2, "fit", "Profile, strengths and concerns", "Best project, what stands out, and what to look at more closely.",
                 f'<div class="card"><p class="quote">{e(r.get("project_summary", ""))}</p></div><div class="grid2" style="margin-top:14px">{strengths}{concerns}</div>{verify_html}'),
            _sec(3, "skills", "Skills matched", "Technologies found in the resume that the role cares about.", f'<div class="card">{_chips(r.get("matched_skills", []))}</div>'),
            _sec(4, "elig", "Eligibility check", "The two hard requirements, decided by rules: genuine Python and real AI / LLM / agentic work.", _eligibility_section(r)),
            _sec(5, "github", "GitHub activity", "Public profile signals, scored out of 10 (5 activity + 5 repositories).", _github_section(r)),
            _sec(6, "claims", "Claims vs. proof", "Technologies named in the resume's projects, searched for in the candidate's public repositories.", _claims_section(r)),
            _sec(7, "evidence", "Evidence log", "The quotes and matched terms behind the scores (expand to read).", _evidence_section(r)),
            _sec(8, "notes", "How this report was produced", "Scoring method and anything that went wrong or was adjusted.", _notes_section(r)),
        ]
        toc_items = [("score", "Score"), ("fit", "Strengths & concerns"), ("skills", "Skills"), ("elig", "Eligibility"), ("github", "GitHub"), ("claims", "Claims vs. proof"), ("evidence", "Evidence"), ("notes", "Method")]
    else:
        sections += [
            _sec(2, "skills", "Skills found", "What the resume does show, for context.", f'<div class="card">{_chips(r.get("matched_skills", []))}</div>'),
            _sec(3, "github", "GitHub activity", "Checked for information only; GitHub never changes eligibility.", _github_section(r)),
            _sec(4, "notes", "How this report was produced", "Why the decision was made and anything to be aware of.", _notes_section(r)),
        ]
        toc_items = [("elig", "Eligibility"), ("skills", "Skills"), ("github", "GitHub"), ("notes", "Method")]

    top = f'<div class="top"><a href="index.html">&larr; All candidates</a><span>Generated {e(generated)}</span></div>'
    footer = ("<footer>Automatically generated from the resume text and public GitHub data. Scores come from a rule-based rubric adjusted "
              "by a bounded LLM review; they support, and do not replace, a recruiter's judgement. Verify important facts with the candidate.</footer>")
    body = top + _header(r, rank_total, badges, ring[0], ring[1], ring[2]) + verdict + _toc(toc_items) + "".join(sections) + footer
    return _page(f"{r.get('candidate_name', 'Candidate')} - screening report", body)


def render_index(results: dict, generated: str) -> str:
    ranked, rejected, s = results["ranked_candidates"], results["rejected_candidates"], results["batch_summary"]
    cohort = cohort_stats(ranked)
    stats = "".join(
        f'<div class="card stat"><b>{v}</b><span>{e(lab)}</span></div>'
        for v, lab in [(s["total_resumes"], "resumes"), (s["eligible"], "eligible"), (s["rejected"], "rejected"),
                       (s.get("needs_human_review", 0), "need human review"), (f"{cohort['mean_total']:.0f}", "average score (eligible)")]
    )
    rows = []
    for r in ranked:
        lab, key = band(r["total_score"])
        flag = ' <span class="badge b-warn">review</span>' if (r.get("eligibility_check") or {}).get("needs_human_review") else ""
        cv = r.get("claim_verification") or {}
        claim = f'{cv["claims_verified"]}/{cv["claims_total"]}' if cv.get("status") == "checked" else "n/a"
        b = r["score_breakdown"]
        rows.append(
            f'<tr><td class="num">{r["rank"]}</td><td><a href="{e(report_filename(r))}">{e(r["candidate_name"])}</a>{flag}</td>'
            f'<td class="num"><span class="minibar"><i style="width:{r["total_score"]}%"></i></span><b>{r["total_score"]}</b></td><td>{e(lab)}</td>'
            f'<td class="num">{b["ai_project_depth"]}</td><td class="num">{b["python_backend"]}</td><td class="num">{b["cloud_fullstack"]}</td>'
            f'<td class="num">{b["github"]}</td><td class="num">{b["engineering_depth"]}</td><td class="num">{claim}</td></tr>'
        )
    rej_rows = "".join(
        f'<tr><td><a href="{e(report_filename(r))}">{e(r["candidate_name"])}</a>'
        + (' <span class="badge b-warn">review</span>' if (r.get("eligibility_check") or {}).get("needs_human_review") else "")
        + f'</td><td>{e("; ".join(r.get("rejection_reasons", [])))}</td></tr>' for r in rejected
    )
    body = (
        f'<div class="top"><span>AI Resume Screening</span><span>Generated {e(generated)}</span></div>'
        f'<div class="hero" style="grid-template-columns:1fr"><div><h1>Candidate screening overview</h1><div class="meta"><span>{e(s.get("scoring_method", ""))}</span></div></div></div>'
        f'<div class="grid5">{stats}</div>'
        '<section><h2>Ranked candidates</h2><p class="sub">Click a name for the full report. Columns: AI depth /40, Python &amp; backend /30, Cloud /15, GitHub /10, Engineering /5, claims confirmed on GitHub.</p>'
        '<div class="card tw"><table class="idx"><thead><tr><th>#</th><th>Candidate</th><th>Total</th><th>Match</th><th>AI</th><th>Py</th><th>Cloud</th><th>GH</th><th>Eng</th><th>Claims</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></section>'
        f'<section><h2>Rejected ({len(rejected)})</h2><p class="sub">Failed the hard requirements: genuine Python and real AI / LLM / agentic work.</p>'
        f'<div class="card tw"><table class="idx"><thead><tr><th>Candidate</th><th>Reason</th></tr></thead><tbody>{rej_rows}</tbody></table></div></section>'
        '<footer>Reports are decision support generated automatically; see each report for the evidence behind its numbers.</footer>'
    )
    return _page("Candidate screening overview", body)


def write_reports(results: dict, out_dir: Path) -> Path:
    """Write one HTML report per processed resume plus index.html. Returns the folder."""
    folder = Path(out_dir) / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.html"):  # stale reports from earlier runs
        old.unlink()
    generated = datetime.now().strftime("%d %b %Y, %H:%M")
    ranked = results["ranked_candidates"]
    cohort = cohort_stats(ranked)
    for r in ranked + results["rejected_candidates"]:
        (folder / report_filename(r)).write_text(render_candidate(r, len(ranked), cohort, generated), encoding="utf-8")
    (folder / "index.html").write_text(render_index(results, generated), encoding="utf-8")
    return folder
