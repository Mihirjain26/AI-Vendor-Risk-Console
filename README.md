# Vendor Risk Console

**AI-powered vendor due diligence — turn a company website into a procurement-ready risk dossier in under a minute.**

---

## The Problem

Before any company signs with a new SaaS vendor, someone — legal, procurement, or an overworked engineer — has to manually dig through that vendor's pricing page, security docs, terms of service, and privacy policy to answer a handful of unglamorous but critical questions:

- Are there hidden fees or brutal cancellation terms buried in the pricing page?
- Does this vendor actually have SOC 2 / GDPR compliance, or just a logo on their homepage?
- What does their SLA *not* cover?
- Is this a "Pass," a "Conditional approval with caveats," or a "Fail"?

This process is slow, repetitive, and inconsistent — the answer often depends on which page the reviewer happened to click first, and how much patience they had left by the fifth tab. It doesn't scale past two or three vendors a week, and it's exactly the kind of structured-but-tedious research task that's a natural fit for an LLM — provided the LLM can actually *find* the right pages first, not just summarize whatever's handed to it.

## The Solution

Vendor Risk Console automates the whole pipeline, end to end:

1. **Scrape** the vendor's landing page and every link on it.
2. **Triage** those links with an LLM call that identifies which ones actually matter for due diligence — pricing, security, compliance, terms, privacy, SLA — and resolves relative URLs to absolute ones so nothing gets missed or hallucinated.
3. **Fetch** the content of each relevant page.
4. **Synthesize** everything into a five-section risk dossier — Executive Summary, Pricing & Financial Transparency, Security/Compliance/Privacy Posture, Operational Risks & SLA Gaps, and a Procurement Recommendation that ends in an explicit **Pass / Conditional / Fail** verdict.
5. **Present** it as a structured, tabbed report in a live console UI — not a wall of markdown — with the verdict badge front and center, sources reviewed listed transparently, and a one-click markdown export for whoever needs to file it.

The result: what used to be 30–45 minutes of manual cross-referencing becomes a single input (company name + URL) and a streamed report you can act on immediately.

## What Makes This More Than a Wrapper

- **Two-stage LLM pipeline**, not one prompt doing everything — a triage step decides *what* to read before a synthesis step decides *what it means*. This mirrors how a human analyst actually works, and keeps the final dossier grounded in pages that were deliberately chosen, not arbitrarily scraped.
- **Deterministic verdict extraction** — the system prompt pins an explicit `Verdict: Pass/Conditional/Fail` output, parsed with regex rather than hoping the model's phrasing is consistent.
- **Live model discovery** — the model dropdown queries your API key directly for currently available models instead of hardcoding names that go stale.
- **Hardened scraping** — timeouts, HTTP status checks, absolute URL resolution, and link deduplication, so a slow or broken vendor page fails loudly instead of silently producing a wrong report.

## Stack

| Layer | Tool |
|---|---|
| UI | Streamlit |
| LLM | Gemini, via the OpenAI-compatible endpoint |
| Scraping | BeautifulSoup + requests |
| Config | python-dotenv |

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/<your-username>/AI-Vendor-Risk-Console.git
cd AI-Vendor-Risk-Console
```

**2. Create and activate a virtual environment**

```bash
python -m venv venv
venv\Scripts\Activate.ps1      # Windows PowerShell
# source venv/bin/activate     # macOS/Linux
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Add your API key**

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

**5. Run the app**

```bash
streamlit run app.py
```

## How to Use It

1. Open the sidebar and paste your Gemini API key (or leave it blank if it's already in `.env`).
2. Enter a **vendor name** and **website URL** (e.g., `Stripe`, `https://stripe.com`).
3. Optionally expand **Advanced** to pick a specific model — the list is pulled live from your API key.
4. Click **Run Audit** and watch the pipeline work in real time: fetching the landing page, triaging relevant links, reading each one, then streaming the dossier.
5. Review the verdict badge, browse the five report tabs, and check **Pages reviewed** to see exactly which sources the analysis is based on.
6. Download the full dossier as a `.md` file, or reopen any past audit from the **Audit Log** in the sidebar.

## Limitations

- This is AI-generated analysis — verify pricing, security, and legal claims against the primary source documents before making an actual procurement decision.
- Pages that render pricing or security info via JavaScript (rather than static HTML) won't be captured by the current scraper.
- Verdict accuracy depends on how much a vendor actually publishes; sparse public documentation will produce a thinner (and more cautious) dossier.
