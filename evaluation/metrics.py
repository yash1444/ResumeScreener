"""Run from the project root:  python evaluation/metrics.py
Compares pipeline output with the hand labels in labels.py (single annotator - see EVALUATION.md)."""
import json, sys, statistics as st
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from labels import LABEL, TIER


def load(p):
    d = json.load(open(p, encoding="utf8"))
    allr = {r["filename"][10:12]: r for r in d["ranked_candidates"] + d["rejected_candidates"]}
    return d, allr


def rk(v):
    s = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
            j += 1
        for k in range(i, j + 1):
            r[s[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def sp(x, y):
    a, b = rk(x), rk(y); ma, mb = st.mean(a), st.mean(b)
    return sum((p - ma) * (q - mb) for p, q in zip(a, b)) / ((sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b)) ** .5)


def report(name, path):
    d, m = load(path)
    el = {k for k, r in m.items() if r["eligible"]}
    E = {k for k, v in LABEL.items() if v == "E"}; B = {k for k, v in LABEL.items() if v == "B"}
    M = {k for k, v in LABEL.items() if v == "M"}; N = {k for k, v in LABEL.items() if v == "N"}
    print(f"\n===== {name} =====  eligible={len(el)} rejected={50 - len(el)}")
    print(f" clearly-E (30): eligible {len(E & el)}  | clearly-N (10): rejected {len(N - el)} | Python+ML/none-only (6): eligible {len(M & el)} {sorted(M & el)} | borderline (4): eligible {len(B & el)} {sorted(B & el)}")
    tp = len(E & el); fp_strict = len(el - E); fn = len(E - el)
    print(f" STRICT (E=positive; B,M,N=negative): precision={tp/len(el):.0%} recall={tp/30:.0%} accuracy={(tp + len(N | M | B) - len((N | M | B) & el))/50:.0%}  FP={fp_strict} FN={fn}")
    pos = E | B
    print(f" LENIENT (E+B positive; M,N negative): precision={len(pos & el)/len(el):.0%} recall={len(pos & el)/len(pos):.0%} accuracy={(len(pos & el) + len((M | N) - el))/50:.0%}")
    pos2 = E | B | M
    print(f" VERY LENIENT (E+B+M positive, only N negative): precision={len(pos2 & el)/len(el):.0%} recall={len(pos2 & el)/len(pos2):.0%} accuracy={(len(pos2 & el) + len(N - el))/50:.0%}")
    ks = list(TIER)
    tot = [m[k]["total_score"] for k in ks if m[k]["eligible"]]
    kk = [k for k in ks if m[k]["eligible"]]
    print(f" ranking vs my tiers (n={len(kk)}): spearman(total)={sp([TIER[k] for k in kk], [m[k]['total_score'] for k in kk]):.2f}  spearman(AI-depth only)={sp([TIER[k] for k in kk], [m[k]['score_breakdown']['ai_project_depth'] for k in kk]):.2f}")
    ok = tt = 0
    for i in kk:
        for j in kk:
            if TIER[i] > TIER[j]:
                tt += 1; ok += m[i]["total_score"] > m[j]["total_score"]
    ranked = sorted((k for k in m if m[k]["eligible"]), key=lambda k: -m[k]["total_score"])
    t5 = sum(TIER.get(k) == 3 for k in ranked[:5]); t10 = sum(TIER.get(k) == 3 for k in ranked[:10])
    print(f" pairwise tier-order accuracy={ok/tt:.0%} ({tt} pairs) | top5 tier-A={t5}/5 | top10 tier-A={t10}/10 | non-E in top10: {[k for k in ranked[:10] if k not in E]} | first non-E at rank {min(ranked.index(k) + 1 for k in ranked if k not in E)}")
    for t in (3, 2, 1):
        s = [m[k]["total_score"] for k in kk if TIER[k] == t]
        print(f"   tier {t}: n={len(s)} mean total={st.mean(s):.1f} range {min(s)}-{max(s)}")
    nonE = {k: m[k]['total_score'] for k in el - E}
    print(" mean total: E=%.1f  non-E eligible=%.1f" % (st.mean(m[k]['total_score'] for k in E & el), st.mean(nonE.values())))
    return d, m


report("v1 before keyword fix (hybrid)", "evaluation/results_v1_before_keyword_fix.json")
report("v2 AFTER KEYWORD FIX (hybrid)", "output/results.json")
report("v2 rules-only", "evaluation/results_rules_only.json")
