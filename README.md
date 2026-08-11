# 🛡️ Vendor Risk Console

An AI-powered vendor due diligence and risk assessment tool. Point it at any
company's name and website, and it triages the site, pulls the pages that
actually matter for procurement (pricing, security, compliance, SLA), and
synthesizes a structured, procurement-grade risk dossier — streamed live,
with a **Pass / Conditional / Fail** verdict badge.

🔗 **Live demo:** https://ai-vendor-risk-console.streamlit.app/
*(public demo is capped at 5 audits per session to protect API quota — enter
your own Gemini API key in the sidebar for unlimited use)*


---

## Why this exists

Manual vendor due diligence — reading through a vendor's pricing page, terms
of service, privacy policy, and security claims by hand — is slow and
inconsistent across reviewers. This tool automates the *retrieval and
triage* step (deciding which pages on a vendor's site are actually relevant
to a risk review) and the *synthesis* step (turning scattered page content
into a single structured dossier a procurement or legal team can act on),
while keeping the output auditable: every dossier lists exactly which pages
were reviewed, and the verdict is extracted from a pinned, machine-parseable
line rather than inferred loosely from prose.

---

## How it works

The pipeline runs in four stages:

**1. Landing page fetch**
The target URL is fetched and parsed with BeautifulSoup; scripts, styles,
images, and inputs are stripped out, leaving clean page text.

**2. LLM-driven link triage**
Every link found on the landing page is passed to the model with a prompt
asking it to identify which links are worth reading for a *vendor risk
dossier specifically* — pricing, security/compliance, terms of service,
privacy policy, SLA, and product/documentation pages — rather than
generic content or marketing pages. The model responds with structured JSON
(`{"links": [{"type": ..., "url": ...}]}`), so the app knows not just which
pages to fetch but *why* each one was chosen.

**3. Content aggregation**
Each selected page is fetched and concatenated with the landing page content
into a single combined document (capped at ~8,000 characters to keep the
prompt within a reasonable size and cost).

**4. Structured dossier generation + verdict extraction**
The combined content is sent to the model with a system prompt that pins an
exact 5-section report structure:

1. Executive Summary & Core Value Proposition
2. Pricing & Financial Transparency
3. Security, Compliance & Data Privacy Posture
4. Operational Risks & SLA Gaps
5. Procurement Recommendations — ending in a single pinned line:
   `Verdict: Pass` / `Verdict: Conditional` / `Verdict: Fail`

The response streams live into the UI. Once complete, the app splits it into
sections using the pinned `## N. Title` headers, and extracts the verdict by
matching specifically on the `Verdict: ...` line (not by scanning the whole
section for the bare words "pass"/"fail", which would false-positive on
prose like *"cancellation terms could fail to meet enterprise needs"*).

---

## Features

- **Live streaming generation** — the dossier renders token-by-token as it's
  generated, not as a single blocking call.
- **Verdict badge + stat cards** — Pass/Conditional/Fail rendered as a
  color-coded pill, alongside sources-reviewed and section counts.
- **Tabbed report view** — each of the 5 sections gets its own tab
  (Overview, Pricing, Security & Compliance, Operational Risk,
  Recommendation) for fast scanning.
- **Source transparency** — every page the model actually read is listed as
  a pill, so the dossier's claims are traceable back to a specific URL.
- **Markdown export** — the full dossier can be downloaded as a `.md` file.
- **Audit log** — past audits from the session are listed in the sidebar and
  can be reopened without re-running the pipeline.
- **Live model discovery** — the sidebar can fetch the list of models
  actually available to your API key (via a manual refresh, not on every
  keystroke, to avoid firing API calls before the key is even fully typed).
- **Session usage cap** — the public demo limits audits per session to
  protect the shared API key from quota exhaustion or abuse; visitors can
  bring their own key for unlimited use.

---

## Stack

| Layer | Tool |
|---|---|
| UI / app framework | [Streamlit](https://streamlit.io) |
| LLM access | [OpenAI Python SDK](https://github.com/openai/openai-python), pointed at Gemini's OpenAI-compatible endpoint |
| Model | Gemini (configurable per-request, live-fetched from your API key) |
| Web scraping | [Requests](https://requests.readthedocs.io) + [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) |
| Config | `python-dotenv` for local environment variables |

No agent framework is used here by design — this is a fixed, deterministic
4-stage pipeline (fetch → triage → aggregate → synthesize), not a dynamic
agent loop, since a due-diligence dossier needs a predictable, repeatable
structure rather than open-ended tool-calling.

---

## Project structure

```
.
├── app.py              # Streamlit UI + pipeline orchestration
├── scraper.py           # fetch_website_contents / fetch_website_links
├── requirements.txt
├── .env                 # local-only, gitignored — GEMINI_API_KEY
└── README.md
```

---

## Running locally

```bash
git clone https://github.com/<your-username>/vendor-risk-console.git
cd vendor-risk-console

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

python -m pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your-key-here
```

Then run:

```bash
streamlit run app.py
```

You can also skip `.env` entirely and paste your API key directly into the
sidebar at runtime — it's never written to disk or logged.

---

## Deployment

Deployed on **Streamlit Community Cloud**, built directly from this repo's
`requirements.txt`. The API key is injected via Streamlit Cloud's **Secrets**
manager (`GEMINI_API_KEY`), never committed to the repository.

---

## Security notes

- API keys are never logged, printed, or embedded in exported files.
- Exceptions are logged server-side only; the UI shows a generic error
  message rather than raw exception text, since provider-side error bodies
  can occasionally echo back request context.
- The model-list cache excludes the API key from its cache-key hash.
- The public demo enforces a per-session audit cap to limit exposure of the
  shared demo key to quota exhaustion.

---

## Limitations

- Verdicts and dossier content are AI-generated and should be treated as a
  first-pass triage, not a substitute for legal/compliance review — always
  verify pricing, security, and legal claims against primary source
  documents before a real procurement decision.
- Link triage depends on the model correctly identifying relevant pages from
  link text/URLs alone; sites with unconventional navigation or JS-rendered
  links (not present in static HTML) may be under-covered, since the scraper
  does not execute JavaScript.
- Content per page is not separately capped before aggregation, so very
  large individual pages can crowd out other sources within the combined
  8,000-character prompt limit.

---

## License

MIT