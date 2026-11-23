import traceback

import streamlit as st

from core.generate import company_snapshot, pick_model
from core.rag import retrieve
from core.search import search_company

st.set_page_config(page_title="HappyInterviews", page_icon="🎯", layout="centered")

st.title("🎯 HappyInterviews")
st.subheader("Your AI interview prep assistant")
st.caption("Phase 1 preview: company snapshot with sources.")

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

    try:
        with st.status("Preparing your report...", expanded=True) as status:
            st.write("🔎 Searching the web...")
            pages = search_company(company, location)
            if not pages:
                status.update(label="No sources found", state="error")
                st.error("Couldn't find usable information about this company. Check the spelling?")
                st.stop()

            st.write(f"📚 Reading {len(pages)} pages and finding the most relevant parts...")
            query = f"{company} business overview, products, scale, recent news, work culture"
            chunks = retrieve(pages, query, top_k=6)
            if not chunks:
                status.update(label="Nothing relevant found", state="error")
                st.error("The pages found didn't contain usable text. Try again later.")
                st.stop()

            st.write("✍️ Writing your snapshot...")
            snapshot, sources = company_snapshot(company, role, location, chunks)
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

    st.caption(f"Model: {pick_model()} · {len(pages)} pages read · {len(chunks)} chunks used")

    with st.expander("🔧 Debug: retrieved chunks"):
        for c in chunks:
            st.markdown(f"**[{c['num']}] score {c['score']}**: {c['title']}")
            st.text(c["text"][:600])
            st.divider()
