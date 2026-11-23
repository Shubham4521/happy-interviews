import time
import traceback

import streamlit as st

from core.generate import company_snapshot
from core.llm import pick_model
from core.planner import plan_queries
from core.rag import build_index, reranker_available, retrieve_for_section
from core.search import run_searches
from core.sections import SECTIONS

st.set_page_config(page_title="HappyInterviews", page_icon="🎯", layout="centered")

st.title("🎯 HappyInterviews")
st.subheader("Your AI interview prep assistant")
st.caption("Phase 2 preview: smart search + per-section retrieval. Full report arrives in Phase 3.")

with st.form("inputs"):
    company = st.text_input("Company", placeholder="e.g. Swiggy")
    role = st.text_input("Role", placeholder="e.g. Data Analyst")
    location = st.text_input("Location", placeholder="e.g. Bengaluru")
    submitted = st.form_submit_button("Generate", type="primary")

if submitted:
    company, role, location = company.strip(), role.strip(), location.strip()
    if not (company and role and location):
        st.warning("Please fill in company, role and location.")
        st.stop()

    timings = {}
    try:
        with st.status("Preparing your report...", expanded=True) as status:
            t = time.perf_counter()
            st.write("🧭 Planning searches...")
            plan = plan_queries(company, role, location)
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
            timings["Embedding"] = time.perf_counter() - t
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
            timings["Retrieval + reranking"] = time.perf_counter() - t

            t = time.perf_counter()
            st.write("✍️ Writing your company snapshot...")
            snapshot, sources = company_snapshot(
                company, role, location, section_chunks["company_snapshot"])
            timings["Writing"] = time.perf_counter() - t
            status.update(label="Done!", state="complete", expanded=False)
    except Exception as e:
        st.error(f"Something went wrong: {type(e).__name__}: {e}")
        with st.expander("Error details (paste these when asking for help)"):
            st.code(traceback.format_exc())
        st.stop()

    st.markdown(f"## {company}: Company snapshot")
    st.markdown(snapshot)
    st.markdown("#### Sources")
    for s in sources:
        st.markdown(f"[{s['num']}] [{s['title']}]({s['url']})")

    total = sum(timings.values())
    st.caption(
        f"Model: {pick_model()} · {len(pages)} pages · {len(index['chunks'])} chunks · "
        f"reranker: {'on' if reranker_available() else 'off'} · {total:.1f}s total"
    )

    # ---------------- Debug panels (for building and testing) ----------------
    st.divider()
    st.markdown("### 🔧 Debug")

    with st.expander("Search plan"):
        for p in plan:
            badge = "🤖 AI" if p["source"] == "ai" else "📋 template"
            st.markdown(f"- **{p['topic']}** ({badge}): {p['query']}")

    with st.expander("Timing"):
        for step, secs in timings.items():
            st.markdown(f"- {step}: **{secs:.1f}s**")

    with st.expander("Retrieved chunks per section"):
        tabs = st.tabs([cfg["title"] for cfg in SECTIONS.values()])
        for tab, key in zip(tabs, SECTIONS):
            with tab:
                chunks = section_chunks[key]
                if not chunks:
                    st.info("No chunks retrieved for this section.")
                for c in chunks:
                    rr = f" · rerank {c['rerank_score']}" if "rerank_score" in c else ""
                    st.markdown(f"**score {c['score']}{rr}** · {', '.join(c['topics'])} · "
                                f"[{c['title']}]({c['url']})")
                    st.text(c["text"][:500])
                    st.divider()
