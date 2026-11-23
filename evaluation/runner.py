"""Runs one evaluation case end to end and turns the results into metrics."""
import statistics
import time

from core.pipeline import retrieve_all, run_pipeline
from core.profile import make_profile
from core.sections import SECTIONS
from evaluation.judge import evidence_for, extract_claims, judge_claims, judge_relevance

TAG_EMOJI = {"source": "🌐", "profile": "💼", "ai": "💡"}


def _relevance_payload(section_chunks: dict) -> list:
    return [{"sid": f"S{i + 1}", "key": key, "title": SECTIONS[key]["title"],
             "passages": [c["text"] for c in section_chunks.get(key) or []]}
            for i, key in enumerate(SECTIONS) if section_chunks.get(key)]


def _relevance_score(verdicts: dict) -> dict:
    flat = [v for values in verdicts.values() for v in values]
    return {"rated": len(flat), "relevant": sum(flat)}


def run_case(case: dict, provider: str = "auto") -> dict:
    """Builds the report for one case, then judges it. Never raises: errors are recorded."""
    out = {"case": case, "error": None}
    try:
        profile = make_profile(case.get("level", "Not specified"), case.get("round", "All rounds"))
        started = time.perf_counter()
        report = run_pipeline(case["company"], case["role"], case["location"], provider, profile)
        out["latency"] = round(time.perf_counter() - started, 1)
        llm, results = report["llm"], report["results"]

        # Section reliability
        out["sections"] = [{
            "key": k, "provider": r.get("provider"), "fallback": r.get("fallback", False),
            "retried": r.get("retried", False), "failed": bool(r.get("error")), "weak": r.get("weak", False),
            "removed_citations": len(r.get("removed_citations") or []),
        } for k, r in results.items()]

        # Grounding mix: how many points of each kind
        all_text = "\n".join(r.get("text", "") for r in results.values() if not r.get("error"))
        out["tags"] = {name: all_text.count(emoji) for name, emoji in TAG_EMOJI.items()}

        # Citation accuracy (cross-model judged)
        claims, uncited, next_id = [], 0, 1
        for key, r in results.items():
            if r.get("error"):
                continue
            found, n_uncited = extract_claims(r["text"])
            uncited += n_uncited
            items = []
            for c in found:
                items.append({"id": next_id, "section": SECTIONS[key]["title"], "claim": c["claim"],
                              "nums": c["nums"], "evidence": evidence_for(c["nums"], report["section_chunks"][key])})
                next_id += 1
            if items:
                claims += judge_claims(llm, items, r.get("provider"))
        out["claims"] = claims
        out["uncited_web_claims"] = uncited

        # Retrieval relevance: reranker on (what the report used) vs off (same pages, same index)
        on_payload = _relevance_payload(report["section_chunks"])
        off_chunks = retrieve_all(report["index"], case["company"], case["role"], case["location"],
                                  use_rerank=False)
        off_payload = _relevance_payload(off_chunks)
        out["relevance_on"] = _relevance_score(judge_relevance(llm, case["company"], case["role"], on_payload))
        out["relevance_off"] = _relevance_score(judge_relevance(llm, case["company"], case["role"], off_payload))
        out["n_pages"] = report["n_pages"]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    out["finished"] = time.time()
    return out


def _pct(part: float, whole: float):
    return round(100 * part / whole, 1) if whole else None


def summarize(case_results: list) -> dict:
    ok = [r for r in case_results if not r.get("error")]
    claims = [c for r in ok for c in r.get("claims", [])]
    judged = [c for c in claims if c["verdict"] != "judge_failed"]
    count = lambda v: sum(1 for c in judged if c["verdict"] == v)
    sections = [s for r in ok for s in r.get("sections", [])]
    rel_on = [r["relevance_on"] for r in ok if r.get("relevance_on", {}).get("rated")]
    rel_off = [r["relevance_off"] for r in ok if r.get("relevance_off", {}).get("rated")]
    tags = {k: sum(r.get("tags", {}).get(k, 0) for r in ok) for k in TAG_EMOJI}
    latencies = [r["latency"] for r in ok if r.get("latency")]
    small = [s for r in ok if r["case"].get("small") for s in r.get("sections", [])]
    regular = [s for r in ok if not r["case"].get("small") for s in r.get("sections", [])]

    return {
        "cases_run": len(case_results), "cases_ok": len(ok),
        "claims_total": len(claims), "claims_judged": len(judged),
        "supported": count("supported"), "partial": count("partial"), "unsupported": count("unsupported"),
        "citation_accuracy": _pct(count("supported"), len(judged)),
        "supported_or_partial": _pct(count("supported") + count("partial"), len(judged)),
        "self_judged_share": _pct(sum(1 for c in judged if c.get("self_judged")), len(judged)),
        "uncited_web_claims": sum(r.get("uncited_web_claims", 0) for r in ok),
        "fake_citations_removed": sum(s["removed_citations"] for s in sections),
        "relevance_rerank_on": _pct(sum(x["relevant"] for x in rel_on), sum(x["rated"] for x in rel_on)),
        "relevance_rerank_off": _pct(sum(x["relevant"] for x in rel_off), sum(x["rated"] for x in rel_off)),
        "tag_counts": tags,
        "tag_share": {k: _pct(v, sum(tags.values())) for k, v in tags.items()},
        "latency_median": round(statistics.median(latencies), 1) if latencies else None,
        "latency_max": max(latencies) if latencies else None,
        "sections_total": len(sections),
        "fallback_rate": _pct(sum(s["fallback"] for s in sections), len(sections)),
        "retry_rate": _pct(sum(s["retried"] for s in sections), len(sections)),
        "failure_rate": _pct(sum(s["failed"] for s in sections), len(sections)),
        "weak_rate_small_companies": _pct(sum(s["weak"] for s in small), len(small)),
        "weak_rate_other_companies": _pct(sum(s["weak"] for s in regular), len(regular)),
    }


def case_row(r: dict) -> dict:
    """One flat row per case for the results table and CSV."""
    case = r["case"]
    row = {"id": case["id"], "company": case["company"], "role": case["role"], "level": case["level"],
           "round": case["round"], "status": "error" if r.get("error") else "ok"}
    if r.get("error"):
        row["error"] = r["error"]
        return row
    judged = [c for c in r.get("claims", []) if c["verdict"] != "judge_failed"]
    on, off = r.get("relevance_on", {}), r.get("relevance_off", {})
    row.update({
        "latency_s": r.get("latency"),
        "claims": len(judged),
        "citation_accuracy_%": _pct(sum(c["verdict"] == "supported" for c in judged), len(judged)),
        "relevance_on_%": _pct(on.get("relevant", 0), on.get("rated", 0)),
        "relevance_off_%": _pct(off.get("relevant", 0), off.get("rated", 0)),
        "source_points": r.get("tags", {}).get("source"),
        "ai_points": r.get("tags", {}).get("ai"),
        "fallbacks": sum(s["fallback"] for s in r.get("sections", [])),
        "failed_sections": sum(s["failed"] for s in r.get("sections", [])),
        "weak_sections": sum(s["weak"] for s in r.get("sections", [])),
    })
    return row
