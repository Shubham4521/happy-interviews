"""Web search with Tavily. Results are cached for 24 hours to save quota."""
from datetime import date

import streamlit as st
from tavily import TavilyClient

MAX_CHARS_PER_PAGE = 8000  # keeps embedding fast on free hosting


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
        response = client.search(query, max_results=5, include_raw_content=True)
        for r in response.get("results", []):
            url = r.get("url")
            text = (r.get("raw_content") or r.get("content") or "").strip()
            if not url or url in seen_urls or len(text) < 200:
                continue
            seen_urls.add(url)
            pages.append({
                "url": url,
                "title": r.get("title") or url,
                "text": text[:MAX_CHARS_PER_PAGE],
            })
    return pages
