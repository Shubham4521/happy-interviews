"""The hidden evaluation dashboard, opened with ?eval=1 and protected by EVAL_PASSWORD.

Results are kept in server memory as each case finishes, so if the page is
refreshed or the connection drops, "Run" simply continues with the cases left.
"""
import csv
import io
import json
import random
import time

import streamlit as st

from evaluation.cases import CASES, case_label
from evaluation.runner import case_row, run_case, summarize

BATCH_SIZE = 5
PAUSE_BETWEEN_CASES = 10  # seconds, to stay under free-tier rate limits
HUMAN_SAMPLE = 10


@st.cache_resource(show_spinner=False)
def eval_store() -> dict:
    return {"results": {}}


def _password_gate() -> bool:
    expected = st.secrets.get("EVAL_PASSWORD")
    if not expected:
        st.warning("To use this page, add EVAL_PASSWORD to your app's Secrets. The password keeps "
                   "visitors from using up your free search and AI allowances.")
        return False
    if st.session_state.get("eval_unlocked"):
        return True
    entered = st.text_input("Evaluation password", type="password")
    if not entered:
        return False
    if entered != expected:
        st.error("That password doesn't match EVAL_PASSWORD in Secrets.")
        return False
    st.session_state["eval_unlocked"] = True
    return True


def _run(cases: list, store: dict):
    bar = st.progress(0.0)
    status = st.empty()
    for i, case in enumerate(cases):
        status.markdown(f"Running case {i + 1} of {len(cases)}: **{case_label(case)}**")
        store["results"][case["id"]] = run_case(case)
        bar.progress((i + 1) / len(cases))
        if i < len(cases) - 1:
            status.markdown(f"Pausing {PAUSE_BETWEEN_CASES}s to respect free-tier rate limits...")
            time.sleep(PAUSE_BETWEEN_CASES)
    status.markdown(f"Finished {len(cases)} case(s).")


def _metric(col, label, value, suffix="%", delta=None, help_text=None):
    shown = "n/a" if value is None else f"{value}{suffix}"
    col.metric(label, shown, delta=delta, help=help_text)


def _human_check(results: list):
    claims = sorted(
        ({**c, "case": case_label(r["case"])} for r in results for c in r.get("claims", [])
         if c["verdict"] != "judge_failed"),
        key=lambda c: (c["case"], c["id"]))
    if not claims:
        return
    sample = random.Random(42).sample(claims, min(HUMAN_SAMPLE, len(claims)))
    st.markdown("#### Check the judge")
    st.caption("Read each claim and its evidence, then say whether you agree with the judge's verdict. "
               "This measures how far the AI judge can be trusted.")
    answers = []
    for i, c in enumerate(sample):
        with st.container(border=True):
            st.markdown(f"**Claim:** {c['claim']}")
            st.caption(f"{c['case']} | {c['section']}")
            st.text(c["evidence"][:700])
            st.markdown(f"**Judge said:** {c['verdict']}" + (f" ({c['reason']})" if c.get("reason") else ""))
            answers.append(st.radio("Your view", ["Agree", "Disagree"], index=None, horizontal=True,
                                    key=f"human-{c['case']}-{c['id']}"))
    given = [a for a in answers if a]
    if given:
        agree = round(100 * sum(a == "Agree" for a in given) / len(given), 1)
        st.metric("Judge agreement with you", f"{agree}%", help=f"Based on {len(given)} of {len(sample)} reviewed claims")
        st.session_state["judge_agreement"] = {"agree_pct": agree, "reviewed": len(given)}


def render_eval_page():
    st.markdown("## Evaluation")
    st.caption("Runs HappyInterviews on a fixed test set and measures citation accuracy, retrieval "
               "relevance (with and without the reranker), grounding, speed and reliability.")
    if not _password_gate():
        return

    store = eval_store()
    done = store["results"]
    pending = [c for c in CASES if c["id"] not in done]
    st.markdown(f"**{len(done)} of {len(CASES)} cases done.** Each case takes about 1 minute plus a "
                f"{PAUSE_BETWEEN_CASES}s pause. Keep this tab open while it runs.")

    c1, c2, c3 = st.columns(3)
    run_batch = c1.button(f"Run next {min(BATCH_SIZE, len(pending))} cases", type="primary",
                          disabled=not pending, use_container_width=True)
    run_all = c2.button(f"Run all {len(pending)} remaining", disabled=not pending, use_container_width=True)
    reset = c3.button("Start over", disabled=not done, use_container_width=True)

    if reset:
        store["results"] = {}
        st.session_state.pop("judge_agreement", None)
        st.info("Results cleared.")
        return
    if run_batch or run_all:
        _run(pending[:BATCH_SIZE] if run_batch else pending, store)

    results = [store["results"][c["id"]] for c in CASES if c["id"] in store["results"]]
    if not results:
        return
    s = summarize(results)

    st.markdown("### Results")
    r1 = st.columns(4)
    _metric(r1[0], "Citation accuracy", s["citation_accuracy"],
            help_text="Share of Source claims fully supported by the page they cite")
    _metric(r1[1], "Supported or partly", s["supported_or_partial"])
    delta = None
    if s["relevance_rerank_on"] is not None and s["relevance_rerank_off"] is not None:
        delta = f"{round(s['relevance_rerank_on'] - s['relevance_rerank_off'], 1)} pts vs. no reranker"
    _metric(r1[2], "Retrieval relevance", s["relevance_rerank_on"], delta=delta,
            help_text="Share of passages picked for each section that the judge rated useful")
    _metric(r1[3], "Median report time", s["latency_median"], suffix="s")

    r2 = st.columns(4)
    _metric(r2[0], "Points from sources", s["tag_share"].get("source"))
    _metric(r2[1], "Model fallback rate", s["fallback_rate"])
    _metric(r2[2], "Section failure rate", s["failure_rate"])
    _metric(r2[3], "Fake citations removed", s["fake_citations_removed"], suffix="")

    with st.expander("All numbers"):
        st.json(s)
    st.markdown("#### Per case")
    rows = [case_row(r) for r in results]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    unsupported = [(case_label(r["case"]), c) for r in results for c in r.get("claims", [])
                   if c["verdict"] == "unsupported"]
    if unsupported:
        with st.expander(f"Unsupported claims ({len(unsupported)}), useful for improving prompts"):
            for label, c in unsupported:
                st.markdown(f"- **{label}** | {c['section']}: {c['claim']}  \n  _Judge: {c.get('reason', '')}_")

    _human_check(results)

    export = {"summary": s, "judge_agreement": st.session_state.get("judge_agreement"), "cases": results}
    csv_buffer = io.StringIO()
    fields = sorted({k for row in rows for k in row}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    writer = csv.DictWriter(csv_buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    d1, d2 = st.columns(2)
    d1.download_button("Download full results (JSON)", json.dumps(export, indent=2, default=str),
                       file_name="happyinterviews-eval.json", mime="application/json", use_container_width=True)
    d2.download_button("Download table (CSV)", csv_buffer.getvalue(), file_name="happyinterviews-eval.csv",
                       mime="text/csv", use_container_width=True)
