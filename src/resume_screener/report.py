"""Small terminal report (bonus)."""
from __future__ import annotations


def print_report(results: dict, top: int = 10) -> None:
    s = results["batch_summary"]
    print("=" * 78)
    print("BATCH SUMMARY")
    for k in ("total_resumes", "successfully_parsed", "eligible", "rejected", "failed_or_unreadable",
              "duplicates_skipped", "borderline_cases", "second_opinions_obtained", "needs_human_review", "llm_cache", "scoring_method", "github_enrichment", "runtime_seconds"):
        print(f"  {k:<22} {s[k]}")
    print("=" * 78)
    print(f"TOP {min(top, len(results['ranked_candidates']))} CANDIDATES")
    print(f"{'#':>3}  {'Candidate':<26}{'Total':>6}  {'AI':>3} {'Py':>3} {'Cld':>3} {'GH':>3} {'Eng':>3}")
    for r in results["ranked_candidates"][:top]:
        b = r["score_breakdown"]
        print(f"{r['rank']:>3}  {r['candidate_name'][:25]:<26}{r['total_score']:>6}  {b['ai_project_depth']:>3} "
              f"{b['python_backend']:>3} {b['cloud_fullstack']:>3} {b['github']:>3} {b['engineering_depth']:>3}")
    print("-" * 78)
    print(f"REJECTED ({len(results['rejected_candidates'])})")
    for r in results["rejected_candidates"]:
        print(f"  {r['candidate_name'][:26]:<27}{'; '.join(r['rejection_reasons'])[:48]}")
    for f in results["failed_resumes"]:
        print(f"  FAILED {f['filename']}: {f['error']}")
    if results.get("needs_human_review"):
        print("-" * 78)
        print("NEEDS HUMAN REVIEW (LLM second opinion disagrees with the rules; the rule decision still stands)")
        for r in results["needs_human_review"]:
            print(f"  {r['candidate_name'][:24]:<25}rules={r['rules_decision']:<9} {r['llm_reasoning'][:60]}")
