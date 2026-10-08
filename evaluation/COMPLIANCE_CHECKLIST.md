# Compliance checklist against the company's assignment document

Legend: ✅ done and verified · 🟡 partly done / with a caveat · ❌ not done

"Verified" means I ran or inspected it, not just wrote it. Evidence is given in the last column.

## Header
| Requirement | Status | Evidence |
|---|---|---|
| Primary language Python | ✅ | Python 3.11 code base |
| Interface: CLI or FastAPI | ✅ | CLI (`main.py`) plus optional FastAPI (`api.py`) |
| Input about 50 resumes | ✅ | 50 of 50 parsed, 0 failed |
| Output: ranked candidates plus reasons | ✅ | `output/results.json`, `output/results_list.json` |

## 1. Expected pipeline
| Requirement | Status | Evidence |
|---|---|---|
| Ingest every resume in the folder | ✅ | 50 files in, 50 parsed |
| Extract name | ✅ | 49 of 50 exactly right; 1 gives first name only ("Prathamesh" for "Prathamesh Patil") |
| Extract email | ✅ | 50 of 50 correct |
| Extract skills | ✅ | `matched_skills` from a skill vocabulary |
| Extract GitHub URL | 🟡 | 43 of 50 resolved; 7 resumes contain no usable link (for example a link cut off at "github.com/") |
| Extract projects | 🟡 | Projects are parsed into entries and used for scoring, but not emitted as a structured list; only `project_summary` and evidence are output |
| Hard eligibility filters applied before ranking | ✅ | Rule-based, `eligibility.py` |
| Score only eligible candidates | ✅ | Rejected candidates get no score |
| Check GitHub when a profile exists | ✅ | All 43 resolvable profiles looked up successfully |
| Return all candidates with eligibility, evidence, breakdown and rank | ✅ | Rejected candidates carry reasons but no rank or score, by design |

## 2. Input requirements
| Requirement | Status | Evidence |
|---|---|---|
| Folder layout (`resumes/`, `src/`, README, requirements) | ✅ | Matches the example structure |
| PDF support | ✅ | PyMuPDF with a pypdf fallback |
| DOCX / TXT (bonus) | ✅ | Tested: a generated .docx and .txt were both ingested and screened correctly |
| Do not assume one layout | 🟡 | Heading detection measured on the 50 resumes (about 97% precision, 94% recall of core headings); invisible characters, wrapped-line fragments, new heading wordings and scrambled PDF block order were fixed afterwards; still heuristic, and one resume's skills row is not recognised; no OCR for scanned PDFs (they are reported as unreadable, which the document allows) |
| Malformed resume must not crash the batch | ✅ | Tests cover a corrupt PDF and an empty file; they are listed under `failed_resumes` |

## 3. Eligibility (hard filter)
| Requirement | Status | Evidence |
|---|---|---|
| Python evidence required | ✅ | Explicit Python or Python-only frameworks |
| JS / Java / React-only profile rejected | ✅ | All 10 resumes I judged clearly ineligible were rejected |
| Meaningful AI / LLM / RAG / agentic evidence required | ✅ | Must appear inside a project or experience entry; skills-list-only claims do not count |
| Do not reject just because JS / Java / React is also present | ✅ | Unit test `test_js_alongside_python_and_ai_is_fine` |
| Suggested output fields (`candidate`, `eligible`, `rejection_reasons`, `matched_skills`) | ✅ | All present on rejected entries, including the `candidate` alias |
| Accuracy of the filter | 🟡 | vs my own labels: all 30 clear matches kept; 4 borderline profiles still pass (2 flagged for human review); strict accuracy 92% |

## 4. Scoring (100 points)
| Requirement | Status | Evidence |
|---|---|---|
| Weights 40 / 30 / 15 / 10 / 5 | ✅ | `config.py`; validator confirms every category stays within its cap and totals equal the sum |
| Evidence-backed, explainable score | ✅ | Per-category evidence, penalties and notes in `results.json` |
| Penalty of 5-15 for thin LLM-wrapper projects | ✅ | -12 (all AI projects thin) or -5 (some), capped at 15; LLM can add a flag |
| Penalty for tutorial-style projects without ownership | 🟡 | Implemented as a proxy: -5 when AI projects have no ownership verbs, plus the LLM's judgement; not a true tutorial detector |
| No full points for a framework named only in skills | ✅ | Skills-list terms earn 25% of the points, summary 50%, project evidence 100% |
| Strong Python with no AI project must not rank near the top | ✅ | Rejected outright by the filter |
| Deterministic, LLM or hybrid allowed | ✅ | Hybrid; LLM moves each category by at most a few points |
| Ranking quality | 🟡 | Moderate: Spearman 0.56 against my tiers; fine for coarse tiers, noisy for exact order |

## 5. GitHub enrichment
| Requirement | Status | Evidence |
|---|---|---|
| Extract username or profile URL from resume | ✅ | Hyperlinks first, then text |
| Use the public GitHub API | ✅ | Repos and public events |
| Signals: recent events, recently updated repos, maintained repos, Python/AI-relevant repos | ✅ | All four used |
| Cap at 10 points (0-5 activity plus 0-5 repos) | ✅ | Matches the suggested split |
| API failure, rate limit, private or missing profile must not fail the batch | ✅ | Tested with a mocked 429; recorded in `github.status` |
| Token from environment variable, never hard-coded | ✅ | `GITHUB_TOKEN`; searched the whole project, no secrets outside the git-ignored `.env` |
| Missing GitHub does not fail screening | ✅ | Profile-less candidates score 0 for GitHub and stay eligible |

## 6. AI / LLM usage
| Requirement | Status | Evidence |
|---|---|---|
| Structured output (Pydantic / JSON schema) | ✅ | `LLMAnalysis` and `EligibilityOpinion` |
| Hard eligibility outside the LLM | ✅ | The LLM can only flag borderline cases for human review |
| Evidence or short reasons for key decisions | ✅ | Evidence lists per category in the schema |
| Provider code behind an adapter | ✅ | `ResumeAnalyzer` protocol in `llm.py` |
| API keys from environment variables | ✅ | `OPENAI_API_KEY` |
| One failed model call does not break the batch | ✅ | Test `test_llm_failure_falls_back_to_rules` |
| Text quality of LLM strengths and concerns | 🟡 | Some entries are generic or speculative |

## 7. Required output
| Requirement | Status | Evidence |
|---|---|---|
| JSON preferred | ✅ | `results.json` plus `results_list.json` |
| Entry shape matches the example | ✅ | `results_list.json` has exactly the 10 example keys; validated by `check_format.py` |
| Ranked eligible candidates, highest first | ✅ | Validator confirms ordering |
| Rejected candidates with explicit reasons | ✅ | All 16 |
| Matched skills and short project summary | ✅ | |
| Score breakdown for every eligible candidate | ✅ | |
| GitHub status / summary when a profile exists | ✅ | |
| Batch summary (total, parsed, eligible, rejected, failed) | ✅ | In `batch_summary`; counts reconcile |
| Top level is a bare list as in the example | 🟡 | `results_list.json` is a bare list; `results.json` is an object because it must also hold the batch summary |

## 8. How to run
| Requirement | Status | Evidence |
|---|---|---|
| `python main.py --input ./resumes --output ./output/results.json` | ✅ | Runs exactly as written |
| Optional `POST /screen`, `GET /results` | ✅ | Tested with FastAPI's test client: 404 before a run, 200 after, 404 for a bad folder |
| No frontend | ✅ | |

## 9. Engineering expectations
| Requirement | Status | Evidence |
|---|---|---|
| Clear modules, not one file | ✅ | 10 modules in `src/resume_screener/` |
| Handle malformed resumes, missing fields, duplicates, GitHub and LLM failures | ✅ | All have tests; no duplicates exist in the real dataset, so that case is tested only on synthetic files |
| Avoid repeated network calls | ✅ | GitHub cached in memory and on disk (6 hours), with concurrent lookups de-duplicated; LLM answers cached on disk (`.cache/llm.json`) |
| Bounded async concurrency | ✅ | Semaphores of 5 for LLM and GitHub |
| Config separate from logic | ✅ | `config.py`, `keywords.yaml`, `.env` |
| At least a few tests for eligibility and scoring | ✅ | 21 tests, all passing |
| Explainability over complex maths | ✅ | Additive points with evidence |

## 10. Deliverables
| Requirement | Status | Evidence |
|---|---|---|
| Source code in a Git repo or ZIP | ❌ | The folder is not a git repository and no ZIP exists yet; **still to do** |
| README with setup and run instructions | ✅ | |
| `requirements.txt` or `pyproject.toml` | ✅ | Fixed: `pypdf` was missing and has been added; a clean virtual environment now installs, passes all 21 tests and runs the pipeline |
| `.env.example` with no real secrets | ✅ | Lists all variables, all blank |
| Generated `results.json` for the provided resume set | ✅ | `output/results.json` |
| README section "Design Decisions" (filtering, scoring, LLM, GitHub) | ✅ | |
| README section "If I Had More Time" (2-4 items) | ✅ | 4 items |
| No secrets in the submission | 🟡 | `.env` holds your real keys and must be left out of the ZIP |

## 12. Scope guardrails and bonus ideas
| Item | Status |
|---|---|
| No frontend, auth, database, deployment or vector DB | ✅ |
| DOCX parsing | ✅ |
| Simple FastAPI endpoints | ✅ |
| Bounded-concurrency processing | 🟡 (built, but the speed-up was never measured) |
| Caching GitHub / LLM results | ✅ (GitHub: memory + disk, 6 h; LLM: disk, keyed on model, prompts, schema and input; measured 56 s cold vs 8 s warm) |
| Terminal report | ✅ |
| HTML report per resume (beyond the terminal report) | ✅ (`output/reports/`: 50 reports + `index.html`; 5 tests) |
| Unit tests with synthetic resumes | ✅ |

## Beyond the document (added enhancement)
| Item | Status | Evidence |
|---|---|---|
| Claim-vs-proof: resume technologies checked against the candidate's GitHub repos | ✅ | `claim_check.py`; 4 unit tests; `claim_verification` in `results.json`; bonus capped at +3, never a penalty; GitHub total stays within the document's 10-point cap |
| Honest about its own limits | ✅ | Each record carries `check_scope`; summary says "not confirmed does not mean false"; spot-check: 2 false negatives in 12 conclusive tests (see `EVALUATION.md`) |
| Improves ranking accuracy | ❌ | No measurable change against my labels (see `EVALUATION.md`); value is evidence and transparency |

## Open items
1. Create the ZIP (or a git repo) excluding `.env`, `.cache` and other local files. **Required.**
2. Decide whether to state in the submission note that scores are good for coarse tiers, not fine ordering.
3. Optional: emit a structured `projects` list per candidate.
