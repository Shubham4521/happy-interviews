"""One place for talking to the LLM (Groq for now; Gemini fallback comes in Phase 3)."""
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


def chat(system: str, user: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
    response = get_client().chat.completions.create(
        model=pick_model(),
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()
