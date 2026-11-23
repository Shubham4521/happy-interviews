"""One place for talking to the LLMs: Groq and Google Gemini.

Speed design:
- "Auto" mode splits the report's sections between Groq and Gemini, so neither
  free tier gets overloaded and both work at the same time.
- No waiting on rate limits: if a model is busy or slow, we switch to the other
  one immediately (no retry pauses, short timeouts).
- Reasoning/"thinking" is turned down where supported, since these are writing
  tasks, not puzzles.

LLM(mode) sets up both providers on the main thread. chat() makes no Streamlit
calls, so it's safe to use from parallel worker threads.
"""
import re

import streamlit as st
from groq import Groq

PROVIDERS = {"auto": "Auto (fastest: uses both)", "groq": "Groq", "gemini": "Google Gemini"}
REAL_PROVIDERS = ("groq", "gemini")
CALL_TIMEOUT_SECONDS = 30

GROQ_SKIP = ("guard", "whisper", "tts", "playai", "orpheus", "distil", "safeguard")
GROQ_PREFERRED = ("llama-3.3-70b", "gpt-oss-120b", "70b", "versatile", "llama")
GEMINI_SKIP = ("image", "tts", "audio", "live", "embedding", "native", "vision",
               "learnlm", "gemma", "robotics", "computer-use")


# ---------------- Provider setup (cached, runs on the main thread) ----------------

@st.cache_resource(show_spinner=False)
def _groq_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"], max_retries=0, timeout=CALL_TIMEOUT_SECONDS)


@st.cache_resource(show_spinner=False)
def _groq_model() -> str:
    if st.secrets.get("GROQ_MODEL"):
        return st.secrets["GROQ_MODEL"]
    models = _groq_client().models.list()
    ids = [m.id for m in (getattr(models, "data", None) or [])]
    chat_models = [i for i in ids if not any(w in i.lower() for w in GROQ_SKIP)]
    for pref in GROQ_PREFERRED:
        for model_id in chat_models:
            if pref in model_id.lower():
                return model_id
    if not chat_models:
        raise RuntimeError("No Groq chat models found")
    return chat_models[0]


@st.cache_resource(show_spinner=False)
def _gemini_client():
    from google import genai
    try:
        from google.genai import types
        return genai.Client(api_key=st.secrets["GEMINI_API_KEY"],
                            http_options=types.HttpOptions(timeout=CALL_TIMEOUT_SECONDS * 1000))
    except Exception:
        return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


def _gemini_rank(name: str):
    """Prefer stable 'flash' models (fast, generous free tier), newest version first."""
    n = name.lower()
    version = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
    return (
        "flash" in n and "lite" not in n,
        not any(w in n for w in ("preview", "exp", "latest")),
        float(version.group(1)) if version else 0.0,
    )


@st.cache_resource(show_spinner=False)
def _gemini_model() -> str:
    if st.secrets.get("GEMINI_MODEL"):
        return st.secrets["GEMINI_MODEL"]
    names = []
    for m in _gemini_client().models.list():
        name = getattr(m, "name", "") or ""
        actions = getattr(m, "supported_actions", None) or []
        if "gemini" not in name.lower() or any(w in name.lower() for w in GEMINI_SKIP):
            continue
        if actions and "generateContent" not in actions:
            continue
        names.append(name)
    if not names:
        raise RuntimeError("No Gemini text models found")
    return max(names, key=_gemini_rank)


# ---------------- Calls (no Streamlit inside: thread-safe) ----------------

def _call_groq(client, model, system, user, temperature, max_tokens) -> str:
    kwargs = dict(
        model=model, temperature=temperature, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    if "gpt-oss" in model.lower():
        kwargs["reasoning_effort"] = "low"  # writing task: little "thinking" needed
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        if "reasoning" not in str(e).lower() or "reasoning_effort" not in kwargs:
            raise
        kwargs.pop("reasoning_effort")  # model/SDK doesn't support it: retry plainly
        response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def _call_gemini(client, model, system, user, temperature, max_tokens) -> str:
    from google.genai import types
    base = dict(system_instruction=system, temperature=temperature, max_output_tokens=max_tokens)
    configs = []
    if "2.5-flash" in model.lower():
        try:  # turn off "thinking" on 2.5 Flash for speed
            configs.append(types.GenerateContentConfig(
                **base, thinking_config=types.ThinkingConfig(thinking_budget=0)))
        except Exception:
            pass
    configs.append(types.GenerateContentConfig(**base))

    last_error = None
    for config in configs:
        try:
            response = client.models.generate_content(model=model, contents=user, config=config)
            return (getattr(response, "text", None) or "").strip()
        except Exception as e:
            last_error = e
            if "thinking" not in str(e).lower():
                raise
    raise last_error


_CALLERS = {"groq": _call_groq, "gemini": _call_gemini}
_SETUP = {"groq": (_groq_client, _groq_model), "gemini": (_gemini_client, _gemini_model)}


class LLM:
    def __init__(self, mode: str = "auto"):
        self.mode = mode
        self.ready, self.setup_errors = {}, {}
        for name, (get_client, get_model) in _SETUP.items():
            try:
                self.ready[name] = (get_client(), get_model())
            except Exception as e:
                self.setup_errors[name] = f"{type(e).__name__}: {e}"
        first = mode if mode in REAL_PROVIDERS else "groq"
        order = [first] + [p for p in REAL_PROVIDERS if p != first]
        self.order = [p for p in order if p in self.ready]
        if not self.order:
            raise RuntimeError(f"No AI model available. Details: {self.setup_errors}")

    def model_name(self, provider: str) -> str:
        return self.ready[provider][1] if provider in self.ready else "unavailable"

    def preferred_for(self, index: int):
        """In Auto mode, alternate sections between providers to split the load."""
        if self.mode == "auto" and len(self.ready) == 2:
            return REAL_PROVIDERS[index % 2]
        return None

    def chat(self, system: str, user: str, temperature: float = 0.3,
             max_tokens: int = 3000, prefer: str = None) -> dict:
        """Returns {"text", "provider", "model", "fallback", "errors"}."""
        order = self.order
        if prefer in self.ready:
            order = [prefer] + [p for p in self.order if p != prefer]
        errors = []
        for i, provider in enumerate(order):
            client, model = self.ready[provider]
            try:
                text = _CALLERS[provider](client, model, system, user, temperature, max_tokens)
                if text:
                    return {"text": text, "provider": provider, "model": model,
                            "fallback": i > 0, "errors": errors}
                errors.append(f"{provider}: empty answer")
            except Exception as e:
                errors.append(f"{provider}: {type(e).__name__}: {str(e)[:200]}")
        raise RuntimeError("All AI models failed. " + " | ".join(errors))
