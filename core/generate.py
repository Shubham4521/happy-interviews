"""Writes report sections from retrieved chunks. (Phase 2: company snapshot only;
the other five sections arrive in Phase 3.)"""
from core.llm import chat


def number_sources(chunks: list) -> list:
    """Gives each unique URL a number, so a citation like [2] points to one link."""
    sources, url_to_num = [], {}
    for c in chunks:
        if c["url"] not in url_to_num:
            url_to_num[c["url"]] = len(sources) + 1
            sources.append({"num": url_to_num[c["url"]], "url": c["url"], "title": c["title"]})
        c["num"] = url_to_num[c["url"]]
    return sources


SYSTEM_PROMPT = """You are an interview prep researcher. Write ONLY from the numbered
sources provided. After every factual claim, cite its source like [1] or [2][3].
If the sources don't cover something, write "Not found in sources" instead of guessing.
Be concise and specific: names, numbers, dates."""


def company_snapshot(company: str, role: str, location: str, chunks: list):
    sources = number_sources(chunks)
    context = "\n\n".join(f"[{c['num']}] {c['text']}" for c in chunks)
    user_prompt = f"""The candidate is preparing for a {role} interview at {company} ({location}).

Sources:
{context}

Write a company snapshot in markdown with exactly these headings:
### What they do
### Business and scale
### Recent news
### Culture and values
Keep it under 300 words, with a citation after every claim."""

    text = chat(SYSTEM_PROMPT, user_prompt)
    if not text:
        text = "_The model returned an empty answer. Please try again._"
    return text, sources
