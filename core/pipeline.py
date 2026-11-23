"""The full report pipeline, shared by the main page and the evaluation page.

plan searches -> search the web -> chunk + embed -> retrieve per section -> write sections
"""
import time

from core.generate import assign_source_numbers, write_report
from core.llm import LLM
from core.planner import plan_queries
from core.profile import jd_for_planner, level_search_words
from core.rag import build_index, retrieve_for_section
from core.search import run_searches
from core.sections import SECTIONS


class NoDataError(Exception):
    """Not enough usable web material. The message is written for visitors."""


def retrieve_all(index: dict, company: str, role: str, location: str, use_rerank: bool = True) -> dict:
    fmt = {"company": company, "role": role, "location": location}
    return {key: retrieve_for_section(index, cfg["query"].format(**fmt), cfg["topics"],
                                      use_rerank=use_rerank)
            for key, cfg in SECTIONS.items()}


def run_pipeline(company: str, role: str, location: str, provider: str, profile: dict,
                 on_progress=None) -> dict:
    """on_progress(step_index, detail, fraction_done) is called as the pipeline moves along."""
    progress = on_progress or (lambda *args: None)
    timings, results = {}, {}
    llm = LLM(provider)

    progress(0, f"Deciding what to search for about {company}...", None)
    t = time.perf_counter()
    plan = plan_queries(company, role, location, level_search_words(profile),
                        provider, profile["round"], jd_for_planner(profile))
    timings["Planning"] = time.perf_counter() - t

    progress(1, f"Running {len(plan)} searches at once...", None)
    t = time.perf_counter()
    pages = run_searches(plan)
    timings["Searching"] = time.perf_counter() - t
    if not pages:
        raise NoDataError(f"We couldn't find enough public information about {company}. "
                          "Check the spelling, or try the company's full name.")

    progress(2, f"Reading {len(pages)} web pages...", None)
    t = time.perf_counter()
    index = build_index(pages)
    timings["Reading"] = time.perf_counter() - t
    if not index["chunks"]:
        raise NoDataError("The pages we found didn't contain readable text. Please try again in a few minutes.")

    progress(3, "Matching the most useful passages to each part of your report...", None)
    t = time.perf_counter()
    section_chunks = retrieve_all(index, company, role, location)
    sources = assign_source_numbers(section_chunks)
    timings["Matching"] = time.perf_counter() - t

    total = len(SECTIONS)
    progress(4, f"Writing {total} sections at once: 0 of {total} ready", 4 / 5)
    t = time.perf_counter()
    for result in write_report(llm, company, role, location, section_chunks, profile):
        results[result["key"]] = result
        ready = sum(1 for r in results.values() if not r["error"])
        progress(4, f"Writing {total} sections at once: {ready} of {total} ready", (4 + ready / total) / 5)
    timings["Writing"] = time.perf_counter() - t

    return {
        "results": results, "sources": sources, "plan": plan, "timings": timings,
        "section_chunks": section_chunks, "n_pages": len(pages), "n_chunks": len(index["chunks"]),
        "failed": sum(1 for r in results.values() if r["error"]),
        "setup_errors": llm.setup_errors, "created": time.time(),
        "index": index, "llm": llm,  # used by the evaluation; dropped before storing a page report
    }
