# AI Resume Screening & Ranking System

Ingests a folder of resumes (PDF required, DOCX/TXT supported), applies a **rule-based Python + AI eligibility filter**
(with an advisory **LLM second opinion on borderline cases**), scores eligible candidates on a **100-point rubric**
(rules + a bounded LLM judgement), enriches with **public GitHub activity**, and writes a ranked, evidence-backed
`results.json`.

## Quick start

```bash
pip install -r requirements.txt
python main.py --input ./resumes --output ./output/results.json
```

Then open **`output/reports/index.html`** in a browser (the overview of every candidate) and **`output/results.json`** (the full
machine-readable result). On the 50 sample resumes you should see: 50 parsed, 0 failed, 34 eligible, 16 rejected, about 10
borderline cases, and a few candidates flagged for human review. A cold run takes about a minute with an OpenAI key (the LLM
calls dominate); a repeat run takes a few seconds thanks to the caches. Without any keys it still works (see "Running without
keys" below). Exact scores can differ by a few points from the shipped `output/` files because LLM output varies slightly
between runs.

## Requirements

* Python 3.10 or newer (developed and tested on 3.11, Windows 11). No other system software is needed.
* Optional: an OpenAI API key (LLM scoring and the eligibility second opinion) and a GitHub token (higher API limits).
  Both are read from environment variables or a `.env` file, never from the code.

## Setup

macOS / Linux:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows (PowerShell):
```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env` and fill in the keys you want (all are optional):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enables LLM-assisted scoring and the eligibility second opinion. Without it the pipeline runs rules-only. |
| `OPENAI_MODEL` | Model name (default `gpt-4o-mini`). |
| `GITHUB_TOKEN` | Optional. Lifts GitHub's unauthenticated limit (60 req/h) to 5000 req/h. |
| `KEYWORDS_FILE` | Optional path to an alternative keyword vocabulary (default: `src/resume_screener/keywords.yaml`). |
| `LLM_CONCURRENCY`, `GITHUB_CONCURRENCY` | Optional. Maximum parallel LLM / GitHub requests (default 5 each). |

Get an OpenAI key at platform.openai.com. For GitHub, create a fine-grained personal access token with read-only access to public
repositories (Settings, Developer settings, Personal access tokens). Never commit `.env`; it is git-ignored.

### Running without keys

* **No `OPENAI_API_KEY`:** the pipeline runs rule-based only (same as `--no-llm`): eligibility is unchanged, scores come from the
  rubric alone, and there are no LLM summaries, strengths or concerns beyond simple rule-based text.
* **No `GITHUB_TOKEN`:** GitHub's anonymous limit is 60 requests per hour, enough for about 3-4 candidates with the claim check.
  Further lookups are recorded as rate-limited or skipped (`github.status`, `claim_verification.status`) and the batch still
  completes; GitHub points then default to 0 for those candidates.

## Run

```bash
python main.py --input ./resumes --output ./output/results.json     # CLI (prints a terminal report too)
python main.py --no-llm                                             # deterministic, no API calls
python main.py --no-second-opinion                                  # LLM scoring, but no eligibility second opinion
python main.py --no-llm-cache                                       # always call the LLM (ignore .cache/llm.json)
python -m pytest -q                                                 # 44 tests (no network needed)
python evaluation/metrics.py                                        # compare output with hand labels (see evaluation/EVALUATION.md)
uvicorn api:app                                                     # optional: POST /screen, GET /results
```

Optional API (after `uvicorn api:app`): `POST /screen` with `{"input_dir": "resumes", "use_llm": false}` runs the pipeline and
returns the batch summary; `GET /results` returns the latest full result. PowerShell example:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/screen -ContentType "application/json" -Body '{"input_dir":"resumes","use_llm":false}'
```

Every run writes two JSON files and a folder of HTML reports:

* **`output/results_list.json`** is the format from section 7 of the assignment: a bare JSON list of the ranked candidates,
  each with exactly `rank, candidate_name, eligible, total_score, score_breakdown, matched_skills, project_summary,
  github_summary, strengths, concerns`.
* **`output/results.json`** is the full version, an object with `batch_summary` (total, parsed, eligible, rejected, failed...),
  `ranked_candidates` (the same entries plus per-category evidence, penalties, GitHub details and `eligibility_check` for
  borderline cases, and `claim_verification`), `rejected_candidates` (explicit `rejection_reasons`; the name appears under both `candidate` and
  `candidate_name`), `needs_human_review`, `failed_resumes` and `duplicates`.

* **`output/reports/`** has one HTML report per resume (eligible and rejected) plus `index.html`, an overview table with links.
  Open `output/reports/index.html` in any browser. Each report is a single self-contained file (inline CSS, no JavaScript,
  no external requests; light/dark theme, mobile-friendly, print-friendly) with these sections: header with status, rank and
  score; a suggested next step (display bands: 80+ Excellent, 65-79 Strong, 50-64 Moderate, below 50 Weak; decision support
  only); score breakdown with bars, cohort-average markers and the evidence behind each category; strengths, concerns and
  "worth verifying in an interview"; matched skills; the eligibility check with Python and AI evidence and any LLM second
  opinion; GitHub activity; claims vs. proof; the evidence log; and how the report was produced. Rejected candidates get the
  reasons, the evidence found, skills and GitHub information.

`python evaluation/check_format.py` validates both JSON files against the assignment's format.

## Layout

```
main.py                    CLI                       api.py   optional FastAPI wrapper
src/resume_screener/
  config.py                weights, thresholds, env settings (no logic)
  keywords.yaml            EDITABLE keyword / regex vocabularies (Python, AI, backend, cloud, skills, section headings)
  keywords.py              loads + validates keywords.yaml (clear error on a bad regex or missing section)
  ingestion.py             PDF/DOCX/TXT reading, hyperlink capture, per-file error isolation, de-duplication
  extraction.py            name/email/GitHub/skills, section + project-block splitting
  eligibility.py           hard Python + AI filter (pure rules) + borderline detection
  scoring.py               deterministic rubric with evidence and project-quality penalties
  llm.py                   provider adapter (OpenAI): scoring + eligibility second opinion, Pydantic structured output
  github_client.py         bounded-concurrency, cached, failure-tolerant GitHub enrichment (+ repo contents)
  html_report.py           per-resume HTML reports + index page (self-contained, escaped, no JavaScript)
  claim_check.py           claim-vs-proof: checks the technologies a resume claims against the candidate's GitHub repos
  pipeline.py              orchestration, rule/LLM blending, ranking, batch summary
tests/                     eligibility, scoring, extraction, second opinion, keywords.yaml, resilience (synthetic resumes)
evaluation/                hand labels, metrics script and an honest write-up of how well the output matches them
```

## Where to change things

| To change | Edit |
|---|---|
| Which words count as Python / AI / backend / cloud evidence, skill names, section headings | `src/resume_screener/keywords.yaml` (no code change; validated on start-up) |
| Scoring weights, penalties, point values, GitHub windows, claim-check bonus, LLM adjustment limits | `src/resume_screener/config.py` |
| Allow classical-ML-only profiles to be eligible (off by default), model name, concurrency, cache and second-opinion switches | `Settings` in `src/resume_screener/config.py`, or the `.env` / command-line flags above |
| LLM prompts and the provider | `src/resume_screener/llm.py` (provider code is isolated in `OpenAIAnalyzer`; implement `analyze` and `second_opinion` to swap it) |

## Troubleshooting and notes

* **`MuPDF error: library error: ...` lines in the terminal** come from one or two sample PDFs with damaged embedded fonts. They are
  harmless: the text is still extracted and every resume is processed.
* **A file listed under `failed_resumes`** was unreadable (empty, corrupt, password-protected, or a scanned image with no text; there is
  no OCR). The rest of the batch is unaffected.
* **`github.status` is `rate_limited` or `partial`:** set `GITHUB_TOKEN`, or wait an hour. Results are cached for 6 hours in `.cache/`.
* **Scores differ slightly between runs:** LLM output varies. The LLM cache makes a re-run on the same input reproducible; delete
  `.cache/` (or pass `--no-llm-cache`) to force fresh LLM answers.
* **A candidate marked "Needs human review":** the rule-based decision stands; the LLM second opinion disagreed, so check that resume.
* **Personal data:** the resumes, `output/results.json` and the HTML reports contain candidates' names and contact details, and
  `.cache/` holds text derived from the resumes. Keep the repository private, and delete `.cache/` before sharing a copy.
* How well the output matches a hand-labelled sample (single annotator) is written up honestly in `evaluation/EVALUATION.md`;
  `evaluation/COMPLIANCE_CHECKLIST.md` maps every requirement of the assignment to where it is met.

## Design Decisions

**Filtering: rules decide, the LLM can only flag.** A resume has to show two things, and both are judged by transparent rules
rather than by a model. The first is genuine Python: the word itself, or a Python-only framework such as FastAPI, Django or
LangGraph, found outside the education and certification sections (LangChain alone does not count, because JavaScript ports
exist). The second is real AI work: an LLM, RAG/embeddings or agent signal inside a project or job entry, since a keyword that
sits only in a skills list proves very little. Knowing JavaScript, Java or React as well is perfectly fine, whereas classical ML
alone (CNNs, OpenCV) is rejected by default because the brief asks for LLM, RAG and agentic work. Every rejection arrives with
explicit reasons.

**Scoring: 100 points, every one of them explainable.** The weights are the brief's own: AI depth 40, Python and backend 30,
cloud and full stack 15, GitHub 10, engineering depth 5. Evidence counts for more or less depending on where it is found: in full
inside a project or job, by half in the summary, and by a quarter when it merely sits in a skills list, so name-dropping earns
little. AI depth rewards distinct capabilities (retrieval, agents, evaluation, state and workflow) and a bonus for several
substantive projects, while thin wrappers around a single LLM call, or projects described without any sign of ownership, are
docked 5 to 15 points.

**LLM usage: a bounded assistant, not the judge.** A small provider adapter asks the model for schema-validated JSON with evidence
quotes: a view on project quality, a summary, strengths and concerns. The model can nudge each rule-based category by only a few
points and can never change eligibility. Calls run with bounded concurrency, retries and caching, and if one fails that resume
quietly falls back to its rule-based scores, with the failure recorded in its notes.

**GitHub scoring: ten points, never a gate.** The username is taken from the resume's hyperlinks first, then its text. Up to 5
points reward recent activity (public events in the last 90 days) and up to 5 reward repositories: non-fork repos pushed within the
last year, with extra credit for Python or AI-relevant ones. A missing, private, rate-limited or failing profile scores 0, is
recorded in `github.status`, and neither affects eligibility nor stops the batch.

*The rest of the design, covering the details behind these four decisions plus the keyword file, the second opinion, claim
verification, caching and reliability, follows in the next section.*

## Additional design details

**Filtering in detail.** Classical-ML-only profiles can be let through by setting `allow_classical_ml=True` in `config.py`; they are then eligible but capped at 12 of 40 AI-depth points, so they cannot rank near the top. JavaScript, Java or React alongside Python and real AI work never counts against a candidate.

**Editable vocabularies (`keywords.yaml`).** Every word list and regex the rules use (Python and AI terms, backend/cloud
/engineering terms, skill names, section headings) lives in `src/resume_screener/keywords.yaml`, one commented
section per list. Changing what counts as "AI evidence" is a YAML edit, with no code change. The file is validated at
start-up (non-empty lists, valid regexes, required sections, anchors that exist) and a mistake stops the run with a message
naming the bad entry. `KEYWORDS_FILE` points to an alternative file. Weights and point values stay in `config.py`.

**LLM second opinion on borderline eligibility (advisory only).** The rules mark a decision as *borderline* when the
evidence is thin: Python appears only in a skills list, or the AI evidence is two or fewer distinct LLM/retrieval/agent
terms inside project entries (eligible cases), or a Python candidate has AI keywords only in the skills/summary (a near-miss
rejection). For those cases only, the LLM answers two narrow questions with a quoted-evidence schema (`EligibilityOpinion`):
*is Python genuine?* and *did the candidate build with LLMs/RAG/agents, as opposed to merely using AI coding tools or doing
classical ML?* **The rule-based decision is always the final one.** If the opinion disagrees, the candidate is only marked
`needs_human_review` (listed in a top-level `needs_human_review` array, mentioned in `concerns`/`notes`, and shown in the
terminal report). If the call fails, or there is no API key, or `--no-second-opinion` is used, the rule decision stands and
the failure is recorded. Every borderline case carries an `eligibility_check` audit record (reasons, rules decision, LLM
answer, agreement).

**Claim-vs-proof verification (resume claims checked against GitHub).** A resume says "built a multi-agent RAG system with
LangGraph"; this step looks for proof. It takes the verifiable technologies named inside the candidate's project and
experience entries (LangGraph, FastAPI, Redis, Docker, pgvector...), picks up to 3 public repos (repos the resume links
to first, then repos whose name matches a project title, then recent Python/AI-relevant repos), and searches each repo's
description/topics, README, **dependency files at the repo root and up to two folders down** (for example
`backend/requirements.txt`, `server/package.json`) and **file/folder names** (for example `CrewAI_Agents/`) for those
technologies. Every confirmed technology records where it was found (`verified_in`). Technologies found in a **fork** do not count, and a repo that was pushed in a single day is not accepted as
proof. The result is a per-candidate `claim_verification` record (technologies verified / not found, which repos were
checked and why, fork and activity facts) and a one-line "Claim check" sentence appended to `github_summary`. It is
**evidence for the reader first and a score input second**: verified claims can add up to **+3 points to AI-depth**
(only when at least 3 claims exist and a real, non-fork repo with history was found), and unverified claims are **never
penalised**, because employer and private code is normal. Each record states its own scope (`check_scope`), and the summary
sentence says that "not confirmed" does not mean "false". Failures (rate limit, private repo, network) produce
`status: skipped/error` and never affect the batch.

**Scoring in detail.** Weights follow the brief: AI depth 40, Python/backend 30, cloud/full-stack 15,
GitHub 10, engineering depth 5. Each term is weighted by *where* it is seen: 100% in a project/experience entry, 50% in
the summary, 25% if only listed in skills, so keyword lists earn little. AI depth rewards distinct capabilities
(retrieval 9, agents 9, evaluation 5, LLM use 5, state/workflow 4, ...) plus a bonus for ≥2 substantive AI projects.
**Penalties** (up to 15): −12 when every AI project looks like a thin LLM-API wrapper (no retrieval/agents/state/eval/backend
logic), −5 when only some do, −5 when projects are described without any ownership/implementation verbs. Strong
Python with no AI project cannot pass the filter, and classical-ML-only profiles are rejected (or capped, if enabled).

**LLM usage in detail.** The LLM judges project quality and writes the summary/strengths/concerns. It is called via a small
`ResumeAnalyzer` adapter (`llm.py`), returns validated Pydantic schemas (`LLMAnalysis`, `EligibilityOpinion`) with evidence
quotes, and runs with bounded concurrency, retries and a timeout. Its category scores are **clamped to ±6 (AI) / ±4 / ±3 / ±1
of the rule-based score**, so results stay predictable and testable, and it can never change eligibility. If a call fails
(or no key is set) that resume silently falls back to rule-based scores and the failure is recorded in `notes`.

**Caching (LLM and GitHub).** LLM answers are cached on disk in `.cache/llm.json` by a provider-independent wrapper around the
adapter (`CachingAnalyzer`). The key is a hash of the call type, model, prompt text, output schema and the exact input, so
changing the model, a prompt or a schema (or the resume text) invalidates old entries automatically. Only successful,
schema-valid answers are stored; failures are never cached, and a corrupt cache file is ignored. Identical input therefore gives
an identical, free answer on re-runs, which also makes results reproducible (LLM output otherwise varies slightly from run to run).
On the 50 sample resumes (60 LLM calls) a cold run took about 56 s and a warm run about 8 s, with identical output. The cache
holds text derived from the resumes, so it lives in the git-ignored `.cache/` folder: delete that folder to purge it (the next run
then calls the LLM again). GitHub lookups are cached in the same folder for 6 hours.

**GitHub scoring in detail.** The username comes from resume hyperlinks first, then text. Two public API calls per user, cached
for the run (and on disk for 6 h so reruns do not burn quota): 0–5 for recent activity (public events in the last 90
days) + 0–5 for repositories (1–2 for non-fork repos pushed in the last 12 months, up to 3 for Python/AI-relevant
ones). Missing, private, rate-limited or failing profiles score 0 and are recorded (`github.status`) without affecting
eligibility or the batch. Without a token the events call is skipped when the quota is low and activity is estimated
from repo push dates (`status: partial`).

**Reliability.** Every file is read in isolation (PyMuPDF → pypdf fallback), scanned/empty files are reported as
failed, byte- and text-level duplicates are skipped, and each candidate is processed inside a guard so one failure never
sinks the batch.

## Known Limitations

* **Keyword vocabularies were a deliberate shortcut, and the first thing we would replace.** Within a short time box we anchored
  eligibility and most scoring signals in curated keyword and pattern lists. They are fast, transparent and perfectly repeatable,
  and they sit in an editable `keywords.yaml` rather than in code, but they remain a hand-written picture of today's vocabulary: a
  tool or phrasing the lists have never met goes unnoticed, an over-broad entry can fire by accident (a coding assistant such as
  "Claude Code" reads as LLM work), and the lists were shaped while looking at the sample resumes. The aim is a generic approach
  that understands what a resume *describes* rather than which words it happens to use: structured extraction of each candidate's
  skills and projects with supporting evidence, semantic instead of literal matching, and thresholds calibrated on human-labelled
  resumes, with the rules kept on as a transparent audit layer. The LLM second opinion softens this only for the borderline cases
  the rules can detect; a confident but wrong rule decision is not re-checked.
* **Section detection is heuristic.** It relies on recognised heading wordings (editable in `keywords.yaml`), a guard against
  wrapped-text fragments, and a page-order re-read for PDFs whose text blocks are stored out of order. Measured on the 50 sample
  resumes: about 97% of detected headings were real and about 94% of real core headings were found before the latest fixes
  (see `evaluation/EVALUATION.md`). Unusual wording, a heading squeezed into one line with other text, or a true multi-column
  layout can still send text to the wrong section.
* **Claim verification does not read source code or commit history.** It reads descriptions, READMEs, dependency files
  (root and up to two folders down) and file/folder names. A technology used only inside source files and mentioned
  nowhere else shows as "not confirmed" (in a spot-check, 2 of 12 unconfirmed claims were really used in the code). A
  technology merely *mentioned* in a README counts as confirmed even if the code does not use it. Treat the result as
  evidence for a reviewer, not as proof either way. It costs up to about 7 GitHub API calls per repo (about 20 per
  candidate), so a `GITHUB_TOKEN` is strongly recommended; when GitHub refuses (rate limit) it degrades to `skipped`.

* The "thin evidence" threshold (two or fewer distinct terms) is a heuristic chosen by hand.
* Scores tie often at the low end and saturate at the top; they suit coarse tiers better than fine ordering.
* See `evaluation/EVALUATION.md` for measured accuracy against hand labels (single annotator, 50 resumes).

## If I Had More Time

1. **A human-labelled benchmark**: `evaluation/` has one annotator's labels for 50 resumes; get several reviewers' labels, measure agreement, and tune weights and `keywords.yaml` against that instead of eyeballing.
2. **Eligibility that generalises beyond keywords**: let a model extract each candidate's skills and projects as structured data with evidence, match them semantically (embeddings) instead of by literal terms, calibrate thresholds on human-labelled resumes, and keep the rules as an audit layer; also run the second opinion on a random sample of confident decisions to estimate how often the rules are confidently wrong.
3. **Deeper claim verification and GitHub signal**: scan source files and commit history (not only READMEs and manifests), map each resume project to exactly one repo, check commit authorship, and add ETag caching.
4. **Better parsing and calibration**: layout-aware extraction (columns, tables), OCR for scanned PDFs, and LLM-judge consistency checks (multi-sample / pairwise) with prompt versioning.

## Notes

- `.env` holds secrets and is git-ignored; never commit it or put it in a submission archive.
- `output/results.json` is the full hybrid run; `output/rules_only.json` is the deterministic (`--no-llm`) baseline.
