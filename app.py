import time
import traceback

import streamlit as st

from core.generate import assign_source_numbers, write_report
from core.llm import LLM, PROVIDERS
from core.planner import plan_queries
from core.rag import build_index, reranker_available, retrieve_for_section
from core.search import run_searches
from core.sections import SECTIONS

REPORT_TTL_SECONDS = 24 * 60 * 60

st.set_page_config(page_title="HappyInterviews", page_icon="🎯", layout="centered")


@st.cache_resource(show_spinner=False)
def report_store() -> dict:
    """Finished reports, shared across visitors for 24 hours: repeat searches load instantly."""
    return {}


with st.sidebar:
    st.markdown("### ⚙️ Settings")
    provider = st.radio(
        "AI model",
        options=list(PROVIDERS),
        format_func=lambda p: PROVIDERS[p],
        help="Auto splits the work between Groq and Gemini for speed. "
             "If a model is busy, the app switches to the other one automatically.",
    )
    fresh = st.checkbox("Always generate a fresh report", value=False,
                        help="Skip saved reports from the last 24 hours.")

st.title("🎯 HappyInterviews")
st.subheader("Your AI interview prep assistant")
st.caption("Phase 3 preview: full 6-section report. Styling arrives in Phase 5.")

with st.form("inputs"):
    company = st.text_input("Company", placeholder="e.g. Swiggy")
    role = st.text_input("Role", placeholder="e.g. Data Analyst")
    location = st.text_input("Location", placeholder="e.g. Bengaluru")
    submitted = st.form_submit_button("Generate report", type="primary")


def build_report(company: str, role: str, location: str, provider: str) -> dict:
    """Runs the whole pipeline, showing progress. Returns everything needed to display it."""
    timings, results = {}, {}
    with st.status("Preparing your report...", expanded=True) as status:
        llm = LLM(provider)  # sets up both models on the main thread

        t = time.perf_counter()
        st.write("🧭 Planning searches...")
        plan = plan_queries(company, role, location, provider=provider)
        timings["Planning"] = time.perf_counter() - t

        t = time.perf_counter()
        st.write(f"🔎 Running {len(plan)} searches in parallel...")
        pages = run_searches(plan)
        timings["Searching"] = time.perf_counter() - t
        if not pages:
            status.update(label="No sources found", state="error")
            st.error("Couldn't find usable information about this company. Check the spelling?")
            st.stop()

        t = time.perf_counter()
        st.write(f"📚 Reading {len(pages)} pages...")
        index = build_index(pages)
        timings["Reading (embedding)"] = time.perf_counter() - t
        if not index["chunks"]:
            status.update(label="Nothing usable found", state="error")
            st.error("The pages found didn't contain usable text. Try again later.")
            st.stop()

        t = time.perf_counter()
        st.write("🎯 Finding the best material for each section...")
        fmt = {"company": company, "role": role, "location": location}
        section_chunks = {
            key: retrieve_for_section(index, cfg["query"].format(**fmt), cfg["topics"])
            for key, cfg in SECTIONS.items()
        }
        sources = assign_source_numbers(section_chunks)
        timings["Retrieval + reranking"] = time.perf_counter() - t

        t = time.perf_counter()
        st.write("✍️ Writing all 6 sections at once...")
        for result in write_report(llm, company, role, location, section_chunks):
            results[result["key"]] = result
            mark = "⚠️" if result["error"] else "✅"
            st.write(f"{mark} {result['title']} ({result['seconds']}s)")
        timings["Writing (parallel)"] = time.perf_counter() - t

        failed = sum(1 for r in results.values() if r["error"])
        status.update(
            label="Done!" if not failed else f"Done, but {failed} section(s) failed",
            state="complete" if not failed else "error",
            expanded=False,
        )

    return {
        "results": results, "sources": sources, "plan": plan, "timings": timings,
        "section_chunks": section_chunks, "n_pages": len(pages),
        "n_chunks": len(index["chunks"]), "failed": failed,
        "setup_errors": llm.setup_errors, "created": time.time(),
    }


def show_report(report: dict, company: str, role: str, location: str, from_cache: bool):
    results, sources, timings = report["results"], report["sources"], report["timings"]

    st.markdown(f"## {company} · {role} · {location}")
    st.caption("🌐 = from the web, with source number · 💡 = AI suggestion")

    tabs = st.tabs([cfg["title"] for cfg in SECTIONS.values()])
    for tab, key in zip(tabs, SECTIONS):
        with tab:
            st.markdown(results[key]["text"])

    with st.expander(f"📎 Sources ({len(sources)})", expanded=False):
        for s in sources:
            st.markdown(f"[{s['num']}] [{s['title']}]({s['url']})")

    if from_cache:
        minutes = int((time.time() - report["created"]) / 60)
        st.caption(f"⚡ Loaded a saved report from {minutes} min ago. "
                   "Tick 'Always generate a fresh report' in the sidebar to rebuild it.")
    else:
        steps = " · ".join(f"{k} {v:.0f}s" for k, v in timings.items())
        st.caption(f"⏱️ {sum(timings.values()):.0f}s total ({steps}) · {report['n_pages']} pages · "
                   f"{report['n_chunks']} chunks · reranker {'on' if reranker_available() else 'off'}")

    # ---------------- Debug panels (for building and testing) ----------------
    st.divider()
    st.markdown("### 🔧 Debug")

    with st.expander("Models used per section"):
        for key in SECTIONS:
            r = results[key]
            if r["error"]:
                st.markdown(f"- **{r['title']}**: ❌ {r['error']}")
                continue
            note = " (fallback)" if r["fallback"] else ""
            weak = " · ⚠️ weak sources" if r["weak"] else ""
            fake = f" · removed fake citations {r['removed_citations']}" if r["removed_citations"] else ""
            st.markdown(f"- **{r['title']}**: {r['model']}{note} · {r['seconds']}s{weak}{fake}")
            for err in r.get("provider_errors") or []:
                st.caption(f"↳ {err}")
        if report["setup_errors"]:
            st.warning(f"Model setup issues: {report['setup_errors']}")

    with st.expander("Search plan"):
        for p in report["plan"]:
            badge = "🤖 AI" if p["source"] == "ai" else "📋 template"
            st.markdown(f"- **{p['topic']}** ({badge}): {p['query']}")

    with st.expander("Retrieved chunks per section"):
        dtabs = st.tabs([cfg["title"] for cfg in SECTIONS.values()])
        for tab, key in zip(dtabs, SECTIONS):
            with tab:
                chunks = report["section_chunks"][key]
                if not chunks:
                    st.info("No chunks retrieved for this section.")
                for c in chunks:
                    rr = f" · rerank {c['rerank_score']}" if "rerank_score" in c else ""
                    st.markdown(f"**[{c['num']}] score {c['score']}{rr}** · {', '.join(c['topics'])} · "
                                f"[{c['title']}]({c['url']})")
                    st.text(c["text"][:500])
                    st.divider()


if submitted:
    company, role, location = company.strip(), role.strip(), location.strip()
    if not (company and role and location):
        st.warning("Please fill in company, role and location.")
        st.stop()

    store = report_store()
    cache_key = (company.lower(), role.lower(), location.lower())
    saved = store.get(cache_key)
    if saved and not fresh and time.time() - saved["created"] < REPORT_TTL_SECONDS:
        show_report(saved, company, role, location, from_cache=True)
        st.stop()

    try:
        report = build_report(company, role, location, provider)
    except Exception as e:
        st.error(f"Something went wrong: {type(e).__name__}: {e}")
        with st.expander("Error details (paste these when asking for help)"):
            st.code(traceback.format_exc())
        st.stop()

    if not report["failed"]:
        store[cache_key] = report  # only keep complete reports
    show_report(report, company, role, location, from_cache=False)
