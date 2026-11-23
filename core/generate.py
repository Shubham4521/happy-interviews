"""Writes the company snapshot with Groq, grounded in retrieved chunks."""
import streamlit as st
from groq import Groq

SKIP_WORDS = ("guard", "whisper", "tts", "playai", "orpheus", "distil", "safeguard")
PREFERRED = ("llama-3.3-70b", "gpt-oss-120b", "70b", "versatile", "llama")


@st.cache_resource(show_spinner=False)
def get_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"])


@st.cache_resource(show_spinner=False)
def pick_model() -> str:
    if st.secrets.get("GROQ_MODEL"):
        return st.secrets["GROQ_MODEL"]
    models = get_client().models.list()
    ids = [m.id for m in (getattr(models, "data", None) or [])]
    chat_models = [i for i in ids if not any(w in i.lower() for w in SKIP_WORDS)]
    for pref in PREFERRED:
        for model_id in chat_models:
            if pref in model_id.lower():
                return model_id
    if not chat_models:
        raise RuntimeError("No chat models found on your Groq account.")
    return chat_models[0]


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

    response = get_client().chat.completions.create(
        model=pick_model(),
        temperature=0.2,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        text = "_The model returned an empty answer. Please try again._"
    return text, sources
