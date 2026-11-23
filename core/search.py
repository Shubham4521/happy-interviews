"""Web search with Tavily, plus basic cleaning. Cached for 24 hours to save quota."""
import re
from datetime import date

import streamlit as st
from tavily import TavilyClient

MAX_CHARS_PER_PAGE = 8000  # keeps embedding fast on free hosting
EXCLUDED_DOMAINS = ["scribd.com", "slideshare.net", "pdfcoffee.com", "studocu.com"]
LONG_TOKEN = re.compile(r"\S{40,}")  # encoded data, long URLs, junk strings


def clean_text(text: str) -> str:
    text = LONG_TOKEN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def looks_like_real_text(text: str) -> bool:
    """True if the text is mostly normal words, not code or encoded data."""
    words = text.split()
    if len(words) < 80:
        return False
    alphabetic_share = sum(w.strip(".,;:!?()\"'").isalpha() for w in words) / len(words)
    return alphabetic_share > 0.6


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def search_company(company: str, location: str) -> list[dict]:
    client = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    year = date.today().year
    queries = [
        f"{company} company overview business model",
        f"{company} latest news {year}",
        f"{company} work culture employees {location}",
    ]

    pages, seen_urls = [], set()
    for query in queries:
        response = client.search(
            query,
            max_results=5,
            include_raw_content=True,
            exclude_domains=EXCLUDED_DOMAINS,
        )
        for r in response.get("results", []):
            url = r.get("url")
            if not url or url in seen_urls:
                continue
            text = clean_text(r.get("raw_content") or "")
            if not looks_like_real_text(text):
                # Fall back to Tavily's short summary if the full page is junk
                text = clean_text(r.get("content") or "")
                if len(text.split()) < 30:
                    continue
            seen_urls.add(url)
            pages.append({
                "url": url,
                "title": r.get("title") or url,
                "text": text[:MAX_CHARS_PER_PAGE],
            })
    return pages
