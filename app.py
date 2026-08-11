"""
Vendor Risk Console
--------------------
An AI-powered vendor due diligence & risk assessment tool.

Given a company name and website, this app:
  1. Crawls the landing page and locates pricing / security / compliance /
     terms / privacy / SLA pages using an LLM link-triage step.
  2. Pulls the content of those pages.
  3. Synthesizes a structured procurement-grade risk dossier, streamed live.
  4. Renders the dossier as a navigable "audit report" with a Pass /
     Conditional / Fail verdict badge, per-section tabs, and an exportable
     markdown file.

Requires `scraper.py` (providing `fetch_website_links` and
`fetch_website_contents`) alongside this file, plus a Gemini API key.
"""

import os
import re
import json
import logging
import traceback
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from scraper import fetch_website_links, fetch_website_contents

# --------------------------------------------------------------------------
# Config & constants
# --------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vendor_risk_console")

st.set_page_config(
    page_title="Vendor Risk Console",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# NOTE: verify these model IDs against the live Gemini model list before
# relying on the default — naming may have moved on since this was written.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODEL_OPTIONS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-pro",
]

LINK_SYSTEM_PROMPT = """
You are provided with a list of links found on a webpage.
You are able to decide which of the links would be most relevant to include in a vendor due diligence and risk assessment dossier about the company.
Prioritize links to: Pricing, Security/Compliance, Terms of Service, Privacy Policy, SLA, About, and Product/Documentation pages.
You should respond in JSON as in this example:

{
    "links": [
        {"type": "pricing page", "url": "https://full.url/goes/here/pricing"},
        {"type": "security page", "url": "https://another.full.url/security"}
    ]
}
"""

LINK_USER_PROMPT_TEMPLATE = """
Here is the list of links on the website {url} -
Please decide which of these are relevant web links for a vendor risk assessment and due diligence dossier,
respond with the full https URL in JSON format.
Focus heavily on Pricing, Security, Compliance, Terms of Service, Privacy, and SLA pages.

Links (some might be relative links):

"""

# Section titles are pinned so the UI can deterministically split the
# streamed markdown into tabs. The numbering + exact wording must match
# SECTION_ORDER below.
SECTION_ORDER = [
    "Executive Summary & Core Value Proposition",
    "Pricing & Financial Transparency",
    "Security, Compliance & Data Privacy Posture",
    "Operational Risks & SLA Gaps",
    "Procurement Recommendations",
]

DOSSIER_SYSTEM_PROMPT = f"""
You are a corporate compliance, procurement, and risk assessment analyst.
You analyze the contents of several key pages from a vendor's website (including pricing, security, terms, privacy, and product pages)
and create a deep vendor due diligence dossier and risk assessment report for internal company operations, legal, and procurement teams.
Respond in markdown without code blocks.

Format your report as exactly five level-2 headers, in this order and wording, each followed by its analysis:
## 1. {SECTION_ORDER[0]}
## 2. {SECTION_ORDER[1]}
## 3. {SECTION_ORDER[2]}
## 4. {SECTION_ORDER[3]}
## 5. {SECTION_ORDER[4]}

Section content requirements:
1. Executive Summary & Core Value Proposition
2. Pricing & Financial Transparency (hidden fees, billing terms, cancellation/refund policies)
3. Security, Compliance & Data Privacy Posture (Certifications like SOC2/GDPR, data residency, privacy red flags)
4. Operational Risks & SLA Gaps
5. Procurement Recommendations — end this section with a single line "Verdict: Pass", "Verdict: Conditional", or "Verdict: Fail"
"""

DOSSIER_USER_PROMPT_HEADER = """
You are auditing a vendor called: {company_name}
Here are the contents of its landing page and other relevant compliance/pricing/security pages;
use this information to build a comprehensive vendor due diligence dossier and risk assessment report in markdown without code blocks.

"""

MAX_PROMPT_CHARS = 8_000

VERDICT_STYLES = {
    "pass": {"icon": "✅", "label": "PASS", "bg": "#0f3d24", "fg": "#4ade80", "border": "#16653a"},
    "conditional": {"icon": "⚠️", "label": "CONDITIONAL", "bg": "#3d2f0a", "fg": "#facc15", "border": "#7a5c0e"},
    "fail": {"icon": "⛔", "label": "FAIL", "bg": "#3d0f14", "fg": "#f87171", "border": "#7a1620"},
    "unknown": {"icon": "❔", "label": "UNVERIFIED", "bg": "#26293b", "fg": "#9ca3af", "border": "#3a3f57"},
}

# --------------------------------------------------------------------------
# Styling — a dark "audit console" theme, deliberately not default Streamlit
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    h1, h2, h3, .hero-title, .card-title { font-family: 'Space Grotesk', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }

    .stApp {
        background: radial-gradient(circle at 15% -10%, #16213a 0%, #0c1120 45%, #060810 100%);
        color: #e7e9ee;
    }

    section[data-testid="stSidebar"] {
        background: #0a0e1a;
        border-right: 1px solid #1e2438;
    }

    #MainMenu, footer { visibility: hidden; }

    .hero-wrap {
        padding: 28px 32px;
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(212,175,55,0.14), rgba(24,32,54,0.4));
        border: 1px solid #262c46;
        margin-bottom: 28px;
    }
    .hero-title { font-size: 2.1rem; font-weight: 700; margin: 0; color: #f4f0e6; letter-spacing: -0.02em; }
    .hero-sub { color: #a8adc0; font-size: 0.98rem; margin-top: 6px; }
    .hero-kicker {
        display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
        letter-spacing: 0.14em; color: #d4af37; text-transform: uppercase;
        border: 1px solid #4a3f1e; padding: 3px 10px; border-radius: 999px; margin-bottom: 10px;
    }

    .verdict-pill {
        display: inline-flex; align-items: center; gap: 8px;
        padding: 8px 18px; border-radius: 999px; font-weight: 600;
        font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; letter-spacing: 0.04em;
        border: 1px solid; margin-bottom: 4px;
    }

    .stat-card {
        background: #10152683; border: 1px solid #232a44; border-radius: 14px;
        padding: 14px 18px; text-align: left;
    }
    .stat-card .label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: #8b91a8; }
    .stat-card .value { font-size: 1.35rem; font-weight: 700; color: #f0f2f8; font-family: 'Space Grotesk', sans-serif; }

    .link-pill {
        display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
        background: #151b30; border: 1px solid #2a3155; color: #b9c0da;
        padding: 4px 10px; border-radius: 8px; margin: 3px 6px 3px 0;
    }

    .report-card {
        background: #0e1322; border: 1px solid #202848; border-radius: 16px;
        padding: 24px 28px; margin-top: 8px;
    }

    .history-item {
        border: 1px solid #232a44; border-radius: 10px; padding: 8px 10px;
        margin-bottom: 6px; font-size: 0.82rem;
    }

    div.stButton > button {
        background: linear-gradient(135deg, #d4af37, #b8860b);
        color: #14100a; font-weight: 700; border: none; border-radius: 10px;
    }
    div.stButton > button:hover { filter: brightness(1.08); }

    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        background: #10152a; border-radius: 10px 10px 0 0; padding: 8px 16px; color: #9aa0b8;
    }
    .stTabs [aria-selected="true"] { color: #f4f0e6 !important; background: #171e38 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Model discovery
# --------------------------------------------------------------------------


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_available_models(_api_key: str) -> list:
    """
    Return the model IDs available to this API key, via the same
    OpenAI-compatible endpoint the rest of the app uses (no extra
    google-generativeai dependency). Cached for an hour per key so
    switching tabs doesn't re-hit the API. Returns [] on any failure
    so the caller can fall back to FALLBACK_MODEL_OPTIONS.

    The leading underscore on `_api_key` tells Streamlit to exclude this
    argument from its cache-key hashing — the key still selects which
    cached result you get (via the function body), but the secret itself
    never becomes part of a hash Streamlit stores or compares.
    """
    if not _api_key:
        return []
    try:
        client = OpenAI(base_url=GEMINI_BASE_URL, api_key=_api_key)
        response = client.models.list()
        return sorted(m.id for m in response.data)
    except Exception:
        return []


# --------------------------------------------------------------------------
# Core pipeline (adapted from the original notebook functions)
# --------------------------------------------------------------------------


def clean_json_block(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return raw


def select_relevant_links(client: OpenAI, model: str, url: str) -> dict:
    links = fetch_website_links(url)
    user_prompt = LINK_USER_PROMPT_TEMPLATE.format(url=url) + "\n".join(links)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": LINK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    raw = clean_json_block(response.choices[0].message.content)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"links": []}

    if "links" not in data and "brochure_links" in data:
        data["links"] = data["brochure_links"]
    elif "links" not in data:
        data["links"] = []

    return data


def build_dossier_prompt(company_name: str, combined_content: str) -> str:
    prompt = DOSSIER_USER_PROMPT_HEADER.format(company_name=company_name) + combined_content
    return prompt[:MAX_PROMPT_CHARS]


def split_into_sections(markdown_text: str) -> dict:
    """Split the streamed report into {section_title: body} using the
    pinned '## N. Title' headers requested in the system prompt."""
    pattern = r"(?m)^##\s*\d+[\.\)]?\s*(.+)$"
    matches = list(re.finditer(pattern, markdown_text))
    sections = {}
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        sections[title] = markdown_text[start:end].strip()
    return sections


def extract_verdict(sections: dict) -> str:
    """
    Look for the pinned 'Verdict: Pass/Conditional/Fail' line specifically,
    rather than scanning the whole Recommendations section for the bare
    words. Scanning the whole section is unsafe: prose like "cancellation
    terms could fail to meet enterprise needs" would false-positive a FAIL
    verdict even when the actual verdict line says Pass.
    """
    rec_text = sections.get(SECTION_ORDER[4], "") or ""
    match = re.search(r"verdict\s*:\s*(pass|conditional|fail)", rec_text, re.IGNORECASE)
    return match.group(1).lower() if match else "unknown"


def run_audit(company_name: str, url: str, api_key: str, model: str):
    client = OpenAI(base_url=GEMINI_BASE_URL, api_key=api_key)

    with st.status("Initializing audit pipeline...", expanded=True) as status:
        status.write(f"🔎 Fetching landing page for **{company_name}**...")
        landing_contents = fetch_website_contents(url)

        status.update(label="Triaging site for pricing / security / compliance pages...")
        link_data = select_relevant_links(client, model, url)
        relevant_links = link_data.get("links", [])

        if relevant_links:
            status.write(f"📎 Located {len(relevant_links)} relevant pages")
        else:
            status.write("⚠️ No additional relevant pages located — auditing landing page only")

        combined = f"## Landing Page:\n\n{landing_contents}\n## Relevant Links:\n"
        for link in relevant_links:
            status.write(f"↳ Reading **{link.get('type', 'page')}** — `{link.get('url', '')}`")
            try:
                page_content = fetch_website_contents(link["url"])
            except Exception as exc:
                logger.warning("Failed to fetch link %s: %s", link.get("url", ""), exc)
                page_content = "[Could not fetch this page]"
            combined += f"\n\n### Link: {link.get('type', 'page')}\n{page_content}"

        status.update(label="Compiling due diligence dossier...")
        user_prompt = build_dossier_prompt(company_name, combined)

        stream_box = st.empty()
        full_response = ""
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": DOSSIER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if delta:
                full_response += delta
                stream_box.markdown(full_response)

        status.update(label="Dossier complete", state="complete")

    stream_box.empty()
    return full_response, relevant_links


# --------------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------------


def render_hero():
    st.markdown(
        """
        <div class="hero-wrap">
            <div class="hero-kicker">AI Vendor Due Diligence</div>
            <p class="hero-title">Vendor Risk Console</p>
            <p class="hero-sub">Point it at any vendor's website — it triages the site, pulls pricing,
            security, and compliance pages, and returns a procurement-ready risk dossier with a
            Pass / Conditional / Fail verdict.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_verdict_pill(verdict: str):
    style = VERDICT_STYLES[verdict]
    st.markdown(
        f"""
        <span class="verdict-pill" style="background:{style['bg']};color:{style['fg']};border-color:{style['border']};">
            {style['icon']} VERDICT: {style['label']}
        </span>
        """,
        unsafe_allow_html=True,
    )


def render_stat_card(col, label, value):
    with col:
        st.markdown(
            f"""<div class="stat-card"><div class="label">{label}</div><div class="value">{value}</div></div>""",
            unsafe_allow_html=True,
        )


def render_source_pills(links):
    if not links:
        st.caption("No supplementary pages were fetched — audit relied on the landing page only.")
        return
    pills = "".join(
        f"<span class='link-pill'>{l.get('type', 'page')}</span>" for l in links
    )
    st.markdown(pills, unsafe_allow_html=True)


def render_report(company_name: str, url: str, report_md: str, links: list, timestamp: str):
    sections = split_into_sections(report_md)
    verdict = extract_verdict(sections)

    render_verdict_pill(verdict)
    st.markdown(f"#### {company_name}")
    st.caption(f"`{url}` · audited {timestamp}")

    c1, c2, c3 = st.columns(3)
    render_stat_card(c1, "Sources Reviewed", len(links) + 1)
    render_stat_card(c2, "Sections Generated", len(sections) if sections else 1)
    render_stat_card(c3, "Verdict", VERDICT_STYLES[verdict]["label"])

    st.markdown("**Pages reviewed:**")
    render_source_pills(links)
    st.write("")

    if sections and all(title in sections for title in SECTION_ORDER):
        tabs = st.tabs(["📋 Overview", "💳 Pricing", "🔐 Security & Compliance", "⚙️ Operational Risk", "✅ Recommendation"])
        for tab, title in zip(tabs, SECTION_ORDER):
            with tab:
                st.markdown(f'<div class="report-card">{sections[title]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="report-card">{report_md}</div>', unsafe_allow_html=True)

    st.download_button(
        "⬇ Download full dossier (.md)",
        data=report_md,
        file_name=f"{company_name.replace(' ', '_')}_vendor_dossier.md",
        mime="text/markdown",
        use_container_width=False,
    )

    st.caption(
        "⚠️ AI-generated analysis. Verify pricing, security, and legal claims against primary "
        "source documents before making a procurement decision."
    )


# --------------------------------------------------------------------------
# App state & sidebar
# --------------------------------------------------------------------------

if "history" not in st.session_state:
    st.session_state.history = []
if "current" not in st.session_state:
    st.session_state.current = None
if "live_models" not in st.session_state:
    st.session_state.live_models = []
if "live_models_key" not in st.session_state:
    st.session_state.live_models_key = None

with st.sidebar:
    st.markdown("### 🛡️ Vendor Risk Console")
    st.caption("AI due diligence & procurement risk triage")
    st.divider()

    api_key_input = st.text_input(
        "Gemini API key",
        value="",
        type="password",
        help="Leave blank to use default environment/.env key, or enter a custom key.",
    )
    company_name = st.text_input("Vendor / company name", placeholder="e.g. Acme Cloud Inc.")
    target_url = st.text_input("Vendor website URL", placeholder="https://www.example.com")

    with st.expander("Advanced"):
        active_key = api_key_input or os.getenv("GEMINI_API_KEY", "")

        # Model list is only fetched when the user explicitly clicks refresh —
        # not on every keystroke in the API key field. Streamlit reruns the
        # whole script on every widget interaction, so an unconditional call
        # here would fire a live API request (often with a still-incomplete,
        # invalid key) after every character typed.
        refresh = st.button("🔄 Refresh model list", use_container_width=True)
        if refresh and active_key:
            fetch_available_models.clear()
            st.session_state.live_models = fetch_available_models(active_key)
            st.session_state.live_models_key = active_key

        live_models = (
            st.session_state.live_models
            if st.session_state.live_models_key == active_key
            else []
        )
        model_options = live_models if live_models else FALLBACK_MODEL_OPTIONS

        if live_models:
            st.caption(f"✅ {len(live_models)} models fetched live from your API key")
        else:
            st.caption("⚠️ Showing offline defaults — click refresh with a valid API key to fetch the live list")

        default_index = model_options.index(DEFAULT_MODEL) if DEFAULT_MODEL in model_options else 0
        model_choice = st.selectbox("Model", model_options + ["Custom..."], index=default_index)
        if model_choice == "Custom...":
            model_name = st.text_input("Custom model name", value=DEFAULT_MODEL)
        else:
            model_name = model_choice

    run_clicked = st.button("Run Audit →", use_container_width=True)

    st.divider()
    st.markdown("**Audit Log**")
    if not st.session_state.history:
        st.caption("Past audits will appear here.")
    else:
        for i, item in enumerate(reversed(st.session_state.history)):
            st.markdown(
                f"""<div class="history-item">
                    <b>{item['company']}</b><br>
                    <span class="mono" style="font-size:0.7rem;color:#8b91a8;">{item['timestamp']}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Reopen", key=f"reopen_{i}", use_container_width=True):
                st.session_state.current = item

# --------------------------------------------------------------------------
# Main flow
# --------------------------------------------------------------------------

render_hero()

if run_clicked:
    api_key = api_key_input or os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("Add a Gemini API key in the sidebar (or set GEMINI_API_KEY in your .env).")
    elif not company_name.strip():
        st.error("Enter a vendor / company name.")
    elif not target_url.strip():
        st.error("Enter a vendor website URL.")
    else:
        url = target_url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        try:
            report_md, links = run_audit(company_name.strip(), url, api_key, model_name.strip() or DEFAULT_MODEL)
            record = {
                "company": company_name.strip(),
                "url": url,
                "report": report_md,
                "links": links,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            st.session_state.history.append(record)
            st.session_state.current = record
        except Exception:
            # Full traceback goes to server-side logs only — never render raw
            # exception text (which can echo request/response context) to the UI.
            logger.error("Audit failed for %s (%s):\n%s", company_name, target_url, traceback.format_exc())
            st.error("Audit failed. Check your API key and the target URL, then try again.")

if st.session_state.current:
    item = st.session_state.current
    render_report(item["company"], item["url"], item["report"], item["links"], item["timestamp"])
else:
    st.info("Enter a vendor name and website in the sidebar, then click **Run Audit** to generate a dossier.")