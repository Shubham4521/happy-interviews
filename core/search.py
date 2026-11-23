"""Web search with Tavily: runs all planned searches in parallel, cleans the text,
removes duplicates, and remembers which topics each page was found for."""
import re
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from tavily import TavilyClient

RESULTS_PER_QUERY = 4
MAX_CHARS_PER_PAGE = 6000  # keeps embedding fast on free hosting
EXCLUDED_DOMAINS = ["scribd.com", "slideshare.net", "pdfcoffee.com", "studocu.com"]
LONG_TOKEN = re.compile(r"\S{40,}")  # encoded data, long URLs, junk strings


def clean_text(text) -> str:
    if not text:
        return ""
    text = LONG_TOKEN.sub(" ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def looks_like_real_text(text: str) -> bool:
    """True if the text is mostly normal words, not code or encoded data."""
    words = text.split()
    if len(words) < 80:
        return False
    alphabetic = sum(w.strip(".,;:!?()\"'").isalpha() for w in words)
    return alphabetic / len(words) > 0.6


def _search_one(client, query: str) -> list:
    try:
        response = client.search(
            query,
            max_results=RESULTS_PER_QUERY,
            include_raw_content=True,
            exclude_domains=EXCLUDED_DOMAINS,
        ) or {}
        return response.get("results") or []
    except Exception:
        return []  # one failed search shouldn't break the whole report


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def run_searches(plan: list) -> list:
    """plan: [{"topic", "query"}, ...] -> pages: [{"url", "title", "text", "topics"}, ...]"""
    client = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        all_results = list(pool.map(lambda p: _search_one(client, p["query"]), plan))

    pages_by_url = {}
    for item, results in zip(plan, all_results):
        for r in results:
            url = r.get("url")
            if not url:
                continue
            if url in pages_by_url:  # same page found by another search
                if item["topic"] not in pages_by_url[url]["topics"]:
                    pages_by_url[url]["topics"].append(item["topic"])
                continue
            text = clean_text(r.get("raw_content"))
            if not looks_like_real_text(text):
                # Fall back to Tavily's short summary if the full page is junk
                text = clean_text(r.get("content"))
                if len(text.split()) < 30:
                    continue
            pages_by_url[url] = {
                "url": url,
                "title": r.get("title") or url,
                "text": text[:MAX_CHARS_PER_PAGE],
                "topics": [item["topic"]],
            }
    return list(pages_by_url.values())
