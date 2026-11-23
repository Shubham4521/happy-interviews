import re
import time
import traceback

import streamlit as st
import streamlit.components.v1 as components

from core.llm import PROVIDERS
from core.pdf_report import build_pdf
from core.pipeline import NoDataError, run_pipeline
from core.profile import LEVELS, ROUNDS, is_personal, make_profile, read_resume
from core.rag import reranker_available
from core.sections import SECTIONS
from ui.theme import (CSS, SCROLL_TO_REPORT_JS, footer_html, hero_html, report_head_html,
                      section_markdown, sources_html, tracker_html)

REPORT_TTL_SECONDS = 24 * 60 * 60
MAX_NEW_REPORTS_PER_HOUR = 5
EXAMPLES = [  # (chip label, company, role, location)
    ("Swiggy, Data Analyst", "Swiggy", "Data Analyst", "Bengaluru"),
    ("Google, Data Scientist", "Google", "Data Scientist", "Bengaluru"),
    ("McKinsey, Business Analyst", "McKinsey & Company", "Business Analyst", "Gurugram"),
    ("HDFC Bank, Data Scientist", "HDFC Bank", "Data Scientist", "Mumbai"),
]

st.set_page_config(page_title="HappyInterviews: AI interview prep", page_icon="🎯", layout="wide")
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
DEBUG = st.query_params.get("debug") == "1"

if st.query_params.get("eval") == "1":  # hidden evaluation dashboard
    from evaluation.page import render_eval_page
    render_eval_page()
    st.stop()


class FriendlyError(Exception):
    """An error whose message is written for visitors."""


@st.cache_resource(show_spinner=False)
def report_store() -> dict:
    """Finished reports, shared across visitors for 24 hours: repeat searches load instantly."""
    return {}


def fill_example(company: str, role: str, location: str):
    st.session_state.update(company=company, role=role, location=location)


def public_profile(profile: dict) -> dict:
    """What the page keeps for display: flags only, never the resume or JD text itself."""
    return {**profile, "jd": "yes" if profile.get("jd") else "", "resume": "yes" if profile.get("resume") else ""}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "report"


# ------------------------------------------------------------------ Hero + inputs
st.markdown(hero_html(), unsafe_allow_html=True)

chips_col, settings_col = st.columns([5, 1], vertical_alignment="bottom")
with chips_col:
    with st.container(key="chips"):
        st.markdown('<p class="chips-label">Try an example</p>', unsafe_allow_html=True)
        for col, (label, *example) in zip(st.columns(len(EXAMPLES)), EXAMPLES):
            col.button(label, on_click=fill_example, args=tuple(example),
                       key=f"ex-{slugify(label)}", use_container_width=True)
with settings_col:
    with st.container(key="settings"):
        with st.popover("Settings", use_container_width=True):
            provider = st.radio("AI model", options=list(PROVIDERS), format_func=lambda p: PROVIDERS[p],
                                help="Auto shares the work between Groq and Gemini, which is fastest. "
                                     "If one is busy, the other takes over.")
            fresh = st.checkbox("Always build a fresh report",
                                help="Skip saved reports from the last 24 hours.")

with st.form("inputs"):
    c1, c2, c3 = st.columns(3)
    company = c1.text_input("Company", key="company", placeholder="Swiggy")
    role = c2.text_input("Role", key="role", placeholder="Data Analyst")
    location = c3.text_input("Location", key="location", placeholder="Bengaluru")
    with st.expander("Personalize your report (optional)"):
        p1, p2 = st.columns(2)
        level = p1.selectbox("Experience level", LEVELS)
        round_type = p2.selectbox("Interview round", ROUNDS)
        jd_text = st.text_area("Job description", height=140,
                               placeholder="Paste the job description to match questions and the checklist to it")
        resume_file = st.file_uploader("Resume (PDF)", type=["pdf"],
                                       help="Used to connect your experience to the company.")
        st.markdown('<div class="hi-privacy">Your resume and job description are used only for this '
                    'report. They are never saved, shared, or sent to the web search.</div>',
                    unsafe_allow_html=True)
    submitted = st.form_submit_button("Build my prep report")

tracker = st.empty()


# ------------------------------------------------------------------ Pipeline
def build_report(company: str, role: str, location: str, provider: str, profile: dict) -> dict:
    def show(step: int, detail: str, progress: float = None):
        tracker.markdown(tracker_html(step, detail, progress), unsafe_allow_html=True)

    try:
        report = run_pipeline(company, role, location, provider, profile, on_progress=show)
    except NoDataError as e:
        raise FriendlyError(str(e))
    finally:
        tracker.empty()

    report.pop("index", None)  # large and only needed by the evaluation
    report.pop("llm", None)
    report["pdf"], report["pdf_error"] = None, None
    try:
        report["pdf"] = build_pdf(company, role, location, profile, report["results"],
                                  SECTIONS, report["sources"])
    except Exception as e:
        report["pdf_error"] = f"{type(e).__name__}: {e}"
    return report


# ------------------------------------------------------------------ Report view
def show_report(view: dict):
    report, profile = view["report"], view["profile"]
    company, role, location = view["company"], view["role"], view["location"]
    results, sources = report["results"], report["sources"]
    sources_by_num = {s["num"]: s for s in sources}

    st.markdown(report_head_html(company, role, location, profile, is_personal(profile)),
                unsafe_allow_html=True)

    meta_col, dl_col = st.columns([3, 1], vertical_alignment="center")
    with meta_col:
        if view["from_cache"]:
            minutes = max(1, int((time.time() - report["created"]) / 60))
            note = (f"Saved report from {minutes} min ago. To rebuild it, open Settings and turn on "
                    "'Always build a fresh report'.")
        else:
            note = (f"Built in {sum(report['timings'].values()):.0f} seconds from "
                    f"{report['n_pages']} web pages.")
        st.markdown(f'<p class="hi-meta">{note}</p>', unsafe_allow_html=True)
    with dl_col:
        if report.get("pdf"):
            with st.container(key="download"):
                st.download_button("Download PDF", data=report["pdf"], mime="application/pdf",
                                   file_name=f"{slugify(company)}-{slugify(role)}-interview-prep.pdf",
                                   use_container_width=True)

    if report["failed"]:
        st.warning(f"{report['failed']} section(s) couldn't be written because the AI services were busy. "
                   "Build the report again in a minute to fill them in.")

    tabs = st.tabs([cfg["title"] for cfg in SECTIONS.values()])
    for tab, key in zip(tabs, SECTIONS):
        with tab:
            st.markdown(section_markdown(results[key]["text"], sources_by_num), unsafe_allow_html=True)

    if sources:
        with st.expander(f"Sources ({len(sources)})"):
            st.markdown(sources_html(sources), unsafe_allow_html=True)

    if DEBUG:
        show_debug(report)


def show_debug(report: dict):
    st.markdown("### Debug")
    timings = report["timings"]
    st.caption(" | ".join(f"{k} {v:.1f}s" for k, v in timings.items())
               + f" | {report['n_chunks']} chunks | reranker {'on' if reranker_available() else 'off'}")
    if report.get("pdf_error"):
        st.warning(f"PDF export failed: {report['pdf_error']}")
    with st.expander("Models used per section"):
        for key in SECTIONS:
            r = report["results"][key]
            if r["error"]:
                st.markdown(f"- **{r['title']}**: failed: {r['error']}")
                continue
            note = (" (fallback)" if r["fallback"] else "") + (" (retried)" if r.get("retried") else "")
            weak = " | weak sources" if r["weak"] else ""
            fake = f" | removed fake citations {r['removed_citations']}" if r["removed_citations"] else ""
            fake += f" | {r['downgraded']} uncited Source point(s) shown as AI tip" if r.get("downgraded") else ""
            st.markdown(f"- **{r['title']}**: {r['model']}{note} | {r['seconds']}s{weak}{fake}")
            for err in r.get("provider_errors") or []:
                st.caption(f"↳ {err}")
        if report["setup_errors"]:
            st.warning(f"Model setup issues: {report['setup_errors']}")
    with st.expander("Search plan"):
        for p in report["plan"]:
            st.markdown(f"- **{p['topic']}** ({p['source']}): {p['query']}")
    with st.expander("Retrieved chunks per section"):
        dtabs = st.tabs([cfg["title"] for cfg in SECTIONS.values()])
        for tab, key in zip(dtabs, SECTIONS):
            with tab:
                for c in report["section_chunks"][key]:
                    rr = f" | rerank {c['rerank_score']}" if "rerank_score" in c else ""
                    st.markdown(f"**[{c['num']}] score {c['score']}{rr}** | {', '.join(c['topics'])} | "
                                f"[{c['title']}]({c['url']})")
                    st.text(c["text"][:500])


# ------------------------------------------------------------------ Submit
if submitted:
    company, role, location = company.strip(), role.strip(), location.strip()
    missing = [name for name, value in (("company", company), ("role", role), ("location", location)) if not value]
    if missing:
        st.warning(f"Add the {' and '.join(missing)} to build your report.")
        st.stop()

    resume_text, resume_note = read_resume(resume_file.getvalue() if resume_file else b"")
    if resume_note:
        st.info(resume_note)
    profile = make_profile(level, round_type, jd_text, resume_text)

    store = report_store()
    cache_key = (company.lower(), role.lower(), location.lower(), profile["level"], profile["round"])
    can_cache = not is_personal(profile)  # reports using a resume or JD stay private
    saved = store.get(cache_key) if can_cache else None

    if saved and not fresh and time.time() - saved["created"] < REPORT_TTL_SECONDS:
        st.session_state["view"] = dict(report=saved, profile=public_profile(profile), company=company,
                                        role=role, location=location, from_cache=True)
        st.session_state["scroll"] = True
    else:
        now = time.time()
        recent = [t for t in st.session_state.get("build_times", []) if now - t < 3600]
        if len(recent) >= MAX_NEW_REPORTS_PER_HOUR:
            wait = int((3600 - (now - min(recent))) / 60) + 1
            st.info(f"You've built {MAX_NEW_REPORTS_PER_HOUR} reports this hour, which keeps this free "
                    f"service available for everyone. You can build another in about {wait} minutes.")
            st.stop()
        try:
            report = build_report(company, role, location, provider, profile)
        except FriendlyError as e:
            tracker.empty()
            st.warning(str(e))
            st.stop()
        except Exception as e:
            tracker.empty()
            st.error("We couldn't finish your report. The free search or AI services may be busy. "
                     "Please try again in a minute.")
            if DEBUG:
                st.code(traceback.format_exc())
            st.stop()
        st.session_state["build_times"] = recent + [now]
        if can_cache and not report["failed"]:
            store[cache_key] = report
        st.session_state["view"] = dict(report=report, profile=public_profile(profile), company=company,
                                        role=role, location=location, from_cache=False)
        st.session_state["scroll"] = True

if st.session_state.get("view"):
    show_report(st.session_state["view"])
    if st.session_state.pop("scroll", False):
        components.html(SCROLL_TO_REPORT_JS, height=0)

st.markdown(footer_html(), unsafe_allow_html=True)
