# Evaluation (honest version)



**There is no ground truth for this assignment.** These numbers compare the pipeline with labels I (one annotator, an AI

assistant) wrote by reading all 50 resumes against a written rubric, *before* looking at the per-candidate scores. They are

a sanity check, not a benchmark: single annotator, 50 samples, subjective tiers, and the labels were not reviewed by a human

recruiter. Reproduce with `python evaluation/metrics.py`; labels are in `evaluation/labels.py`.



## Label groups

| Group | n | Meaning |

|---|---|---|

| E | 30 | Genuine Python **and** a real LLM/RAG/agent/embedding project or job entry |

| B | 4 | Borderline (03, 09, 15, 34) |

| M | 6 | Python but only classical ML/CV or no ML (04, 05, 14, 20, 21, 48) |

| N | 10 | Clearly ineligible (no Python and/or no AI) |



## Eligibility filter

| Setting | Eligible | Recall (E) | Precision, strict | Accuracy, strict |

|---|---|---|---|---|

| `allow_classical_ml=True` (earlier default) | 40 | 30/30 (100%) | 75% | 80% |

| **`allow_classical_ml=False` (current default, `output/results.json`)** | 34 | 30/30 (100%) | 88% | 92% |



* All 10 clearly-ineligible resumes were rejected (JS/Java-only profiles and Python-with-no-AI profiles).

* **The weakness is false positives, not false negatives.** The earlier default admitted the 6 classical-ML/no-ML profiles

  (a policy choice, since reversed) and all 4 borderline ones.

  Turning classical ML off removes the 6 ML-only profiles but not the borderline ones.

* Keyword-stuffing check: appending `LangGraph, RAG, LLMs, OpenAI ...` to the *skills list* of five ineligible resumes, or a

  one-line AI claim to a summary, did not make any of them eligible.



> The ranking tables below were computed with the earlier default (`allow_classical_ml=True`); switching it off does not change which of the 30 clearly-eligible candidates pass, but `output/results.json` was regenerated afterwards, and LLM run-to-run variation moved individual scores slightly (e.g. the top total went from 100 to 89). Re-run `python evaluation/metrics.py` for current ranking numbers.



## Ranking (30 clearly-eligible candidates vs my A/B/C quality tiers)

| Version | Spearman(total, tier) | Pairwise tier-order accuracy | Tier-A in top 5 / top 10 |

|---|---|---|---|

| hybrid, before keyword fix | 0.61 | 80% | 4/5, 7/10 |

| **hybrid, shipped (`output/results.json`)** | **0.57** | **76%** | **3/5, 7/10** |

| rules only (`--no-llm`) | 0.67 | 82% | 5/5, 8/10 |



* Every clearly-eligible candidate outscores every borderline/ML-only one on average (66.9 vs 39.4 mean total); the first

  non-E candidate appears at rank 25 of 40.

* **The LLM did not improve agreement with my labels; rules-only is slightly better.** Differences of ±0.05 Spearman are

  within noise for n=30. The LLM adds about +7 points on average and compresses the top (one candidate scores 100/100).

* The biggest "mistake" (a strong AI/ML engineer ranked ~28th) is mostly a rubric effect: 60% of the rubric is

  backend/cloud/GitHub/engineering, and that profile has little Postgres/Redis/cloud evidence. On the AI-depth category alone the

  correlation with my tiers is higher (0.71).

* Tiers reflect my judgement of AI depth, whereas the rubric also rewards backend, cloud and GitHub, so some disagreement is

  expected even from a perfect implementation.



## Stability and extraction

* Two full LLM runs: 36/40 identical totals, mean |difference| 0.4 points, max 5, identical top 10.

* Email: 50/50 correct. Name: 49/50 exactly right (one returns first name only). GitHub username: 49/50 agree with an

  independent regex; for 1 resume the visible text and the hyperlink name different accounts and the pipeline used the

  hyperlink. 7 resumes have no resolvable GitHub URL.

* GitHub scores cannot be validated against any ground truth. They only show that the profile exists and has recent pushes.



## Bug found by this evaluation

A keyword edit had silently failed, so "Hugging Face", "transformers", "BERT" and "BART" were still treated as LLM evidence

(and backspace characters had corrupted three regexes). Fixed; the eligibility result did not change, ranking moved within noise.



## Known limitations

* Borderline cases (Java-centric profile with Python only in a skills list; "Claude Code" used as a dev tool counted as AI

  evidence; a face-recognition pipeline built on embeddings) are decided by keyword rules, not understanding.

* Scores have many ties at the low end and saturation at the top; they are good for coarse tiers, not fine ordering.

* Section detection is heuristic; unusual layouts can leak skills-list text into "project" evidence.



## LLM second opinion on borderline cases (added later)

The rules flagged 10 of 50 resumes as borderline (all of them rule-eligible): the 4 I had labelled borderline (03, 09, 15, 34)

plus 6 clearly-eligible ones (06, 10, 29, 36, 38, 44) that have thin AI evidence. The LLM answered for all 10:



* It **agreed** with the rules on 8, including all 6 clearly-eligible candidates (no false alarms on clear cases) and on 2 of my

  borderline ones (09, 15).

* It **flagged 2 for human review**: 03 (Agam Jain) and 34 (Nisarga H. S.), both of which I had also labelled borderline and

  considered the weakest eligible candidates. The rule decision still stands for both.

* So on this small sample it caught 2 of the 4 borderline cases and raised no false alarm (n=10; treat as anecdotal).

* Caveat: the "thin evidence" threshold was set after I had seen which resumes were borderline, so this is not an unbiased

  test of the detector. It also never re-checks a confident rule decision that is wrong.



## Claim-vs-proof verification (added last)

For the 34 eligible candidates, the technologies each resume claims in its projects were searched for in up to 3 public

GitHub repos per candidate (README, description, topics, dependency files).



* It produced a report for 27 candidates, found no usable repo for 3, and had no GitHub profile or no claims for 4.

* Example outcomes: one candidate had 8 of 8 claimed technologies confirmed; another had 0 of 9 confirmed, and one of that

  candidate's matching repos was a fork (which proves nothing).

* Effect on the score: at most +3 on AI depth, no penalties. **It did not change agreement with my labels** (Spearman

  with my tiers stayed 0.56), so its value is in the evidence it shows a reviewer, not in better ranking.

* Limitations: source code is not read, so "not confirmed" can be a false negative; I did not manually audit the

  verification results for all 27 candidates.



### Deeper scan and an independent check of the claim verification

A first version only read the top level of each repo. A spot-check found a false negative: a candidate scored 0 of 9 because

the dependency files were in `backend/` and the repo had no README. The check now also reads dependency files up to two folders

down and searches file/folder names, and each record states its scope. That candidate moved from 0 of 9 to 3 of 9 confirmed.



To estimate how often "not confirmed" is wrong, I used GitHub's code search on 7 candidates (up to 4 unconfirmed technologies each,

in up to 2 of the checked repos): **12 conclusive results, 10 correct (technology really absent), 2 false negatives**

(PostgreSQL and vector search used in the code of one candidate's repo). The other 10 queries were inconclusive because GitHub

rate-limited the search endpoint. So roughly 5 in 6 unconfirmed claims in this sample were truly absent from the checked repos,

but the sample is small, covers 7 of 27 checked candidates, and "absent from the checked repos" is not the same as "false" (the

project may live in a repo that was not selected, or in private code).

The opposite error also exists: a technology mentioned in a README counts as confirmed even if the code does not use it.


## Section detection (measured last)
I listed every heading the detector found in all 50 resumes and judged each against the resume text myself (single annotator),
plus the heading-like lines it missed.

| Measure | Result |
|---|---|
| Headings detected | 276, of which 7 were not real headings (precision about 97%) |
| Real core headings missed (summary / skills / projects / experience / education / certifications) | 17 (recall about 94%: 262 found of 279) |
| Resumes where every core section was found and nothing leaked | 33 of 50 (66%) |
| Resumes with minor leaks (a small non-core heading missed, or a stray fragment) | 10 of 50 (20%) |
| Resumes with a core failure (skills / projects / experience text sent to the wrong bucket) | 7 of 50 (14%): candidates 10, 15, 19, 20, 21, 33, 45 |

Causes of the 7 core failures:
* **Invisible characters (10, 45):** headings ending in a zero-width space (U+200B) are not recognised. In candidate 10 the Projects and
  Skills text fell into "Achievements" (an excluded section). Removing the character raised that candidate's rule-based
  Python/backend score from 10 to 24 and AI depth from 14 to 17; eligibility did not change. Candidate 45 was mis-split completely
  but is rejected either way (no Python).
* **Wrapped-line fragments read as headings (15, 33; also 23):** a one-word fragment such as "educational QA", "project" or
  "academic information." was taken as a heading, so the text after it went to the wrong section (for example a job entry
  into the excluded Education section).
* **Heading wording not covered (19, 33):** "Skills Summary" is not recognised, so the skills text lands in Education.
  Also missed: "Core Competencies", "Profile Summary", "Objectives", "Certificates & Achievements".
* **Two-column layouts (20, 21):** the PDF text comes out in column order, so headings are separated from their content and
  almost all text is assigned to the wrong section. Needs layout-aware extraction, not a heading tweak.

Effect on results: none of the 40 resumes I labelled clearly eligible or ineligible changed class because of these errors, but
scores for the affected candidates are probably understated. I quantified this only for candidate 10; for 15, 19, 20, 21 and 33
the effect on scores was not measured. Correction to an earlier statement: the first-name-only result for candidate 35
("Prathamesh") is caused by the name being split across two lines in the PDF, not by section detection.

### Section detection: fixes and re-check
Four fixes were made after the measurement above: (1) invisible zero-width characters are stripped before parsing;
(2) new heading wordings were added to `keywords.yaml` ("Skills Summary", "Core Competencies", "Profile Summary",
"Objectives", "Certificates & Achievements", "Key Achievements", "Open Source", "Involvement" and similar) and the label
"Course" was removed because it is a table label; (3) a one-word fragment is no longer a heading when the line before it is
unfinished text, or when it ends with a full stop or contains a quotation mark; (4) PDFs whose text blocks are stored out of
reading order are also read in page order (top to bottom, left to right), and that order is used only if it produces clearly
more complete sections.

Re-check (by section sizes, not a full re-judging of all 50 resumes by hand):
* All 7 core failures now have sensible sections: 10, 15, 19, 33 and 45 are fixed, and 20 and 21 (scrambled block order) now have their
  skills / projects / summary text in the right places. Candidate 20 is still imperfect: its "SKILLS / LANGUAGES / TOOLS" row is a
  single line with wide gaps and is not recognised, so its skills text sits in the summary section.
* 21 of the 50 resumes had a different section split after the fixes. I reviewed each change. All but a handful are the intended
  improvements; the rest are small shifts of a few characters (invisible characters removed, or a text block moving between
  two sections that both count as work evidence). The review caught one regression, which I fixed: a loose "Certificate"
  heading pattern had cut candidate 25's experience section from 433 to 14 characters.
* Eligibility: no candidate changed eligibility. Accuracy against my labels is unchanged (strict accuracy 92%, recall 100%).
* Scores: candidate 10 rose by 13 points (rank 22 to 11), as predicted, because its Projects and Skills text is now read; 15 rose by 7 and 34 by 6
  (partly from the fixes, partly LLM variation). Candidate 23 fell by 7, but its rule-based evidence is identical before and after, so
  that change is LLM variation. Treat any single score change below about 5 points as noise.
* New tests: 6 section tests (invisible characters, fragments, new wordings, a scrambled PDF, a well-ordered PDF).
