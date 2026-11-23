"""Query planner: the AI writes targeted searches, each tagged with a topic.

It now also uses the candidate's level, interview round and the gist of the JD
(never the resume) to make searches more specific. If the AI's answer is
missing, malformed, or skips a topic, gaps are filled from fixed templates.
"""
import json
import re
from datetime import date

import streamlit as st

from core.llm import LLM
from core.sections import FALLBACK_QUERIES, TOPICS

PLANNER_SYSTEM = """You plan web searches for interview preparation research.
Return ONLY valid JSON, no explanation, in this exact shape:
{"queries": [{"topic": "<topic>", "query": "<search text>"}]}"""


def _tidy(text: str) -> str:
    return " ".join(text.split())


def _fallback(topic, company, role, location, level_words, round_words) -> list:
    year = date.today().year
    return [_tidy(t.format(company=company, role=role, location=location, year=year,
                           level=level_words, round=round_words or "technical"))
            for t in FALLBACK_QUERIES[topic]]


def _parse_json(text: str):
    """Pull the JSON object out of the model's answer, even if wrapped in extra text."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def plan_queries(company: str, role: str, location: str, level_words: str = "",
                 provider: str = "auto", round_type: str = "All rounds",
                 jd_gist: str = "") -> list:
    """Returns [{"topic": ..., "query": ..., "source": "ai" | "template"}, ...]."""
    year = date.today().year
    round_words = "" if round_type == "All rounds" else round_type.lower()
    needs = ", ".join(f'{count} for "{topic}"' for topic, count in TOPICS.items())
    extras = []
    if level_words:
        extras.append(f"Candidate level: {level_words}. Use it in process and questions searches.")
    if round_words:
        extras.append(f"Focus the questions searches on the {round_words} round.")
    if jd_gist:
        extras.append(f"Key parts of the job description (use 1-2 key skills in role_skills "
                      f"and questions searches): {jd_gist}")

    user = f"""Candidate: {role} at {company}, {location}. Current year: {year}.
{chr(10).join(extras)}

Write {sum(TOPICS.values())} web search queries: {needs}.
Topic meanings:
- company: what the company does, business model, size, revenue
- news: latest announcements, launches, results from {year}
- process: interview rounds and candidate interview experiences for this role
- questions: actual interview questions asked for this role at this company
- culture: work culture, employee reviews, values
- role_skills: skills, tools and requirements for this role at this company
Rules: every query must include "{company}"; keep each under 12 words; make them specific."""

    ai_queries = {}
    try:
        answer = LLM(provider).chat(PLANNER_SYSTEM, user, temperature=0.3, max_tokens=600)
        data = _parse_json(answer["text"]) or {}
        for item in data.get("queries") or []:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip().lower()
            query = _tidy(str(item.get("query", "")))
            if topic not in TOPICS or not query or len(query) > 150:
                continue
            if company.lower() not in query.lower():
                query = f"{company} {query}"
            ai_queries.setdefault(topic, [])
            if query not in ai_queries[topic]:
                ai_queries[topic].append(query)
    except Exception:
        ai_queries = {}  # planner failed: use templates for everything

    plan = []
    for topic, count in TOPICS.items():
        chosen = [(q, "ai") for q in ai_queries.get(topic, [])[:count]]
        for q in _fallback(topic, company, role, location, level_words, round_words):
            if len(chosen) >= count:
                break
            if q not in [c[0] for c in chosen]:
                chosen.append((q, "template"))
        plan.extend({"topic": topic, "query": q, "source": src} for q, src in chosen)
    return plan
