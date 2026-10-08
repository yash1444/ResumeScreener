"""Validate output/results.json against the output format in the assignment document (section 7)
and against internal consistency rules. Run from the project root:  python evaluation/check_format.py"""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "output/results.json")
d = json.loads(path.read_text(encoding="utf-8"))
problems, notes = [], []


def check(cond, msg):
    if not cond:
        problems.append(msg)


# ---- document's example entry (section 7)
SPEC_KEYS = ["rank", "candidate_name", "eligible", "total_score", "score_breakdown", "matched_skills",
             "project_summary", "github_summary", "strengths", "concerns"]
SPEC_BREAKDOWN = ["ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"]
CAPS = {"ai_project_depth": 40, "python_backend": 30, "cloud_fullstack": 15, "github": 10, "engineering_depth": 5}
SUMMARY_KEYS = ["total_resumes", "successfully_parsed", "eligible", "rejected", "failed_or_unreadable"]

print("top-level type:", type(d).__name__, "| keys:", list(d) if isinstance(d, dict) else "-")
check(isinstance(d, dict), "top level is not an object")
ranked, rejected = d["ranked_candidates"], d["rejected_candidates"]

# batch summary
s = d["batch_summary"]
for k in SUMMARY_KEYS:
    check(k in s, f"batch_summary missing {k}")
check(s["total_resumes"] == s["successfully_parsed"] + s["failed_or_unreadable"] + s["duplicates_skipped"], "summary: total != parsed+failed+dups")
check(s["successfully_parsed"] == s["eligible"] + s["rejected"], "summary: parsed != eligible+rejected")
check(len(ranked) == s["eligible"] and len(rejected) == s["rejected"], "summary counts differ from list lengths")

# ranked entries
for i, r in enumerate(ranked, 1):
    miss = [k for k in SPEC_KEYS if k not in r]
    check(not miss, f"ranked #{i} {r.get('candidate_name')}: missing spec keys {miss}")
    check(r["rank"] == i, f"rank not sequential at position {i}")
    check(r["eligible"] is True, f"{r['candidate_name']}: eligible should be true")
    b = r["score_breakdown"]
    check(list(b) == SPEC_BREAKDOWN, f"{r['candidate_name']}: breakdown keys/order {list(b)}")
    check(all(isinstance(v, int) and 0 <= v <= CAPS[k] for k, v in b.items()), f"{r['candidate_name']}: breakdown out of range {b}")
    check(isinstance(r["total_score"], int) and r["total_score"] == sum(b.values()), f"{r['candidate_name']}: total != sum(breakdown)")
    check(0 <= r["total_score"] <= 100, f"{r['candidate_name']}: total outside 0-100")
    check(isinstance(r["matched_skills"], list) and all(isinstance(x, str) for x in r["matched_skills"]), f"{r['candidate_name']}: matched_skills")
    check(isinstance(r["strengths"], list) and isinstance(r["concerns"], list), f"{r['candidate_name']}: strengths/concerns not lists")
    check(isinstance(r["project_summary"], str) and r["project_summary"].strip(), f"{r['candidate_name']}: empty project_summary")
    check(isinstance(r["github_summary"], str) and r["github_summary"].strip(), f"{r['candidate_name']}: empty github_summary")
    check(isinstance(r["candidate_name"], str) and r["candidate_name"].strip(), f"rank {i}: empty candidate_name")
scores = [r["total_score"] for r in ranked]
check(scores == sorted(scores, reverse=True), "ranked list is not sorted by total_score desc")
check(len({r["candidate_name"] for r in ranked}) == len(ranked), "duplicate candidate names in ranked list")

# rejected entries (document's "suggested eligibility output": candidate, eligible, rejection_reasons, matched_skills)
for r in rejected:
    check(r["eligible"] is False, f"{r['candidate_name']}: eligible should be false")
    check(r.get("rejection_reasons"), f"{r['candidate_name']}: no rejection_reasons")
    check("matched_skills" in r, f"{r['candidate_name']}: no matched_skills")
    check(r.get("candidate") == r.get("candidate_name") and r.get("candidate"), f"{r.get('candidate_name')}: 'candidate' alias missing or different")
    check("rank" not in r and "total_score" not in r, f"{r['candidate_name']}: rejected entry carries rank/score")

# ---- second file: bare list in exactly the document's shape
list_path = path.with_name(path.stem + "_list" + path.suffix)
if list_path.exists():
    lst = json.loads(list_path.read_text(encoding="utf-8"))
    check(isinstance(lst, list), f"{list_path.name}: top level is not a list")
    check(len(lst) == len(ranked), f"{list_path.name}: {len(lst)} entries vs {len(ranked)} ranked")
    for a, b in zip(lst, ranked):
        check(list(a) == SPEC_KEYS, f"{list_path.name}: keys {list(a)} differ from the document's example")
        check(all(a[k] == b[k] for k in SPEC_KEYS), f"{list_path.name}: entry {a.get('candidate_name')} differs from results.json")
    print(f"{list_path.name}: bare list of {len(lst)} entries, keys exactly = {SPEC_KEYS == list(lst[0]) if lst else '-'}")
else:
    problems.append(f"{list_path} not found")

# GitHub status
gh = [r for r in ranked + rejected if r.get("github")]
check(all(r["github"]["status"] in {"ok", "partial", "not_found", "rate_limited", "error"} for r in gh), "unknown github status")

# every input resume accounted for
names = [r["filename"] for r in ranked + rejected] + [f["filename"] for f in d["failed_resumes"]] + [x["filename"] for x in d["duplicates"]]
check(len(names) == len(set(names)) == s["total_resumes"], f"files accounted for: {len(set(names))} of {s['total_resumes']}")

print(f"ranked={len(ranked)} rejected={len(rejected)} failed={len(d['failed_resumes'])} duplicates={len(d['duplicates'])}")
print("extra keys on ranked entries (beyond the document's example):", sorted(set().union(*[set(r) for r in ranked]) - set(SPEC_KEYS)))
print("\nPROBLEMS:" if problems else "\nNo structural problems found.")
for p in problems:
    print(" -", p)
print("\nNOTES:")
for n in notes:
    print(" -", n)
