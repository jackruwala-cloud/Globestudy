# International Student Advisor (MVP)

A Q&A advisory web app for international students in the U.S., covering **visa,
tax, and financial** questions. The whole point of this product is **trust**:
every answer is traceable to a **primary source** (an official IRS / USCIS /
CFPB page), and when there is no verified source, the app **says so instead of
guessing**.

> ⚠️ **This is a research / informational tool only.** It is **not** licensed
> tax, legal, or immigration advice, it does **not** connect to any bank
> account, it does **not** move money, and it does **not** give personalized
> advice. Always confirm with your school's international student office (DSO)
> and a licensed professional before acting.

---

## Why this is different

Most chatbots will happily generate a plausible-sounding answer about your visa
or taxes from general model knowledge. For international students that's
dangerous — a wrong answer about FICA, OPT unemployment days, or Form 8843 can
have real consequences. This system enforces **citation discipline**:

1. Every answer is built **only** from a small, curated set of official
   government documents that have been retrieved and dated.
2. Every answer ships with **numbered, clickable citations** back to the exact
   source URL and section.
3. If retrieval doesn't find a confident match, the answer is an explicit
   **"I don't have a verified source for this — here's who to ask instead."**
4. A **confidence / coverage indicator** and a **risk-level notice** are shown
   with every answer.

By default the engine runs in **extractive** mode: it composes answers directly
from retrieved source text with **no LLM in the loop**, so it *cannot*
hallucinate. An optional LLM mode (Claude) is available but is still constrained
to answer strictly from the retrieved context.

---

## Scope of the MVP

**Covered (curated primary sources):**

| Topic | Source |
|---|---|
| FICA exemption for F-1/J-1 students | IRS — Foreign Student Liability for SS/Medicare |
| Tax residency & Substantial Presence Test | IRS Publication 519 |
| Form 8843 (statement for exempt individuals) | IRS |
| Form 1042-S (foreign-person U.S. income) | IRS |
| F-1 on-campus employment (20-hr rule) | USCIS / SEVP |
| Curricular Practical Training (CPT) | USCIS / SEVP |
| Optional Practical Training (OPT) | USCIS / SEVP |
| STEM OPT 24-month extension | USCIS / SEVP |
| Sending money abroad (consumer protections) | CFPB |

The source set is **intentionally narrow and high-quality** — depth and
reliability over broad-but-shallow coverage. See "Adding new sources" below to
expand it.

**Explicitly out of scope (by design):**

- Personalized tax / legal / immigration advice
- Investment or financial-product advice
- Bank-account linking, budgeting on your real data, or moving money
- A mobile app

---

## Architecture

```
sources/          Curated, versioned primary-source documents + freshness checker
  documents/*.md    One curated extract per source (public-domain U.S. gov text)
  manifest.json     Source metadata: URL, retrieval date, publisher, summary
  check_freshness.py  Content-hash diff vs. the live pages (flags stale/changed)
ingestion/        Turns sources into a retrievable knowledge base
  chunker.py        Chunks by section/topic (not arbitrary character counts)
  vector_store.py   Retrieval: pure-Python TF-IDF (default) or local Chroma
  build_index.py    Builds data/chunks.json (+ Chroma collection if configured)
qa_engine/        Retrieval-augmented answering with enforced citations
  engine.py         Retrieve -> confidence gate -> cite or refuse -> log
  prompts.py        Disclaimer, high-stakes notice, referrals, LLM prompt
risk_classifier/  Categorizes each question by stakes (HIGH vs LOW)
  classifier.py     Rule-based, logs its reasoning
  rules.yaml        Tunable keyword rules
web_ui/app.py     Chat-style Streamlit UI (citations, confidence, feedback)
admin/app.py      Internal Streamlit view (gaps, feedback, source freshness)
common/           config, paths, JSONL logging
data/             Runtime output (chunks, logs) — git-ignored
```

**Data flow for one question:** classify risk → retrieve top chunks (TF-IDF
cosine) → if top score below the floor, refuse and refer → else compose a cited
answer from the retrieved chunks → attach confidence + risk notice + disclaimer
→ log the question, classification, confidence, and citations.

---

## Setup

Requires Python 3.9+.

```bash
cd intl-student-advisor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: create your own config (secrets stay out of git)
cp config.example.yaml config.yaml
```

Build the knowledge base (chunks the sources and builds the index):

```bash
python -m ingestion.build_index
```

Run the app (chat UI):

```bash
streamlit run web_ui/app.py
```

Run the admin view (in a second terminal):

```bash
streamlit run admin/app.py --server.port 8502
```

Check whether any primary source pages have changed:

```bash
python -m sources.check_freshness            # online content-hash diff
python -m sources.check_freshness --offline  # staleness only, no network
```

There is also a helper: `./run.sh web`, `./run.sh admin`, `./run.sh build`,
`./run.sh freshness`.

---

## Configuration

All settings live in `config.yaml` (copy from `config.example.yaml`). **No API
keys are hardcoded.** Secrets are read from the environment when available:

- `ANTHROPIC_API_KEY` — only needed if you set `qa.mode: llm`.

Key settings:

| Setting | Meaning |
|---|---|
| `retrieval.backend` | `tfidf` (default, offline, no ML deps) or `chroma` |
| `retrieval.min_score` | If the top match is below this, the engine **refuses** to answer |
| `retrieval.support_floor` | How far down to include supporting citations |
| `retrieval.high_conf_score` | At/above this a match is labeled "high confidence" |
| `qa.mode` | `extractive` (default, no LLM) or `llm` (Claude, still context-only) |
| `qa.llm_model` | Model id used in LLM mode |

The confidence thresholds are tuned for the TF-IDF backend against the current
source set. If you add many sources or switch to Chroma, re-check them with a
few sample questions (see below).

---

## Source policy — official sources only (enforced)

The knowledge base is **locked to official sources**. Every source URL in
`sources/manifest.json` is validated against an allowlist by
[`sources/source_policy.py`](sources/source_policy.py), and
`python -m ingestion.build_index` **refuses to build** if any source is not
official. Allowed:

- **U.S. federal government (`.gov`):** IRS, USCIS, DHS/SEVP (incl.
  studyinthestates.dhs.gov), ICE, Department of Labor, Department of State,
  Social Security Administration, CFPB.
- **Accredited universities (`.edu`):** a school's own official
  international-student-office pages (added per school — see below).

Informal sources — blogs, forums, law-firm marketing pages, "study abroad"
aggregators, AI summaries — are rejected automatically. Because the engine only
ever answers from this curated set (it never fetches the open web), this is what
makes "we only cite official sources" an enforced guarantee, not a promise.

To add a specific school's official guidance, add a manifest entry whose `url`
host ends in `.edu` (e.g. your international office's "new students" page). It
passes the policy and becomes citable for that school's students.

**Per-university sourcing.** A manifest source may be `scope: "federal"`
(default — shown to everyone) or `scope: "university"` with a `university_id`
(shown only to students of that school). `POST /ask` takes an optional
`university_id`, and retrieval merges federal sources with that school's `.edu`
sources; the response also carries a `school_context` (the school's
international-office link) so the app can always point a student to their office,
even when no school-specific source is curated yet. See `sources/documents/uiuc_isss.md`
for the template, and `reference/universities.json` for the picker registry
(expandable via `scripts/build_universities.py`).

**Which sources cover what.** Visa/tax answers draw on **USCIS, IRS, DOL, DHS/SEVP,
and the student's university**. DHS/SEVP (Study in the States) is kept because it
is the authority on SEVIS/check-in/CPT/OPT reporting. **CFPB** is used only for
lower-stakes financial-literacy content (e.g. sending money home) and never as a
visa/tax citation.

## Adding new primary sources

Keep the bar high: only add official, authoritative sources (the build enforces this).

1. **Write the curated extract.** Add `sources/documents/<id>.md`. Use `## `
   section headers — the chunker splits on them, so each section should be a
   self-contained, citable idea. Prefer quoting/closely paraphrasing the
   official text (U.S. federal government works are public domain).
2. **Register it in `sources/manifest.json`** with a new entry: `id`, `title`,
   `file`, `url` (the authoritative page), `publisher`, `category`
   (`tax` / `visa` / `finance`), `retrieved_date` (the date you curated it),
   and a one-line `summary`.
3. **Rebuild the index:** `python -m ingestion.build_index`.
4. **Baseline freshness:** `python -m sources.check_freshness`.
5. **Sanity-check retrieval** with a couple of questions that the new source
   should answer, and confirm the confidence thresholds still separate
   in-scope from out-of-scope questions. Adjust `retrieval.*` in `config.yaml`
   if needed.
6. If the new topic introduces new high-stakes vocabulary, add keywords to
   `risk_classifier/rules.yaml`.

---

## Keeping sources fresh

Government pages change. `sources/check_freshness.py` fetches each source URL,
reduces it to visible text, hashes it, and compares against the last recorded
hash:

- **changed** → the live page differs from what we last curated; re-review and
  update the `.md` extract and the `retrieved_date`.
- **stale** → not re-checked within the staleness window (default 30 days).
- **error** → couldn't fetch (e.g. **HTTP 403** — some government sites block
  automated requests). These need a **manual** review at the source URL; the
  admin view flags them.

The admin **Source freshness** tab shows all of this at a glance.

---

## What gets logged (for review)

Everything is plain JSONL in `data/`, so it's easy to inspect:

- `data/qa_log.jsonl` — every question with its risk classification + reasoning,
  confidence, top retrieval score, and which sources were cited.
- `data/feedback.jsonl` — thumbs up/down on each answer.

The **admin** view turns these into:

- **Coverage gaps** — questions with no confident source (ranked by how close
  the best match was — the best candidates for new sources) and low/medium-
  confidence answers.
- **Feedback** — negative feedback to review.
- **Source freshness** — stale / changed / un-checkable sources.

---

## Limitations & honest caveats

- The curated `.md` files are **summaries/extracts** of the official sources,
  not the full original documents. They link to the authoritative page, which
  is always the source of truth — verify there.
- TF-IDF retrieval is keyword-based and deliberately simple/inspectable. It can
  miss a relevant source if the question uses very different wording; that shows
  up as a "no verified source" refusal (safe) rather than a wrong answer.
- Rules, forms, dollar thresholds, and deadlines change. Freshness checking
  reduces but does not eliminate the risk of stale guidance.
- This tool does not know **your** specific facts (dates, program, income). It
  gives general, sourced information — not a determination about your case.
```
