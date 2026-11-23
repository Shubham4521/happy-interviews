"""One place for talking to the LLMs, built to survive free-tier limits.

The work is spread over "slots": several Groq models plus several Gemini
models. Free-tier limits are per model, so spreading sections across models
multiplies the budget.

For every slot we track a cooldown, shared by all visitors:
- a rate limit with "try again in Xs" puts that slot to sleep for X seconds,
- a model with no quota at all ("limit: 0", daily limit) is parked for an hour,
and each slot handles at most 2 requests at a time.

chat() tries the preferred slot, then the others, waits briefly if every slot
is cooling down, and makes no Streamlit calls, so it's safe in worker threads.
"""
import re
import threading
import time

import streamlit as st
from groq import Groq

PROVIDERS = {"auto": "Auto (fastest: uses every available model)", "groq": "Groq first", "gemini": "Gemini first"}
REAL_PROVIDERS = ("groq", "gemini")
CALL_TIMEOUT_SECONDS = 30
MODELS_PER_PROVIDER = 3
PER_SLOT_CONCURRENCY = 2
MAX_WAIT_SECONDS = 25        # longest we'll wait for a cooling slot inside one call
MAX_ATTEMPTS_PER_SLOT = 2
PARKED_SECONDS = 60 * 60     # models with no quota left

GROQ_SKIP = ("guard", "whisper", "tts", "playai", "orpheus", "distil", "safeguard", "compound", "allam")
GROQ_PREFERRED = ("gpt-oss-120b", "llama-3.3-70b", "gpt-oss-20b", "llama-4", "qwen", "kimi", "70b",
                  "versatile", "llama-3.1-8b", "llama")
GEMINI_SKIP = ("image", "tts", "audio", "live", "embedding", "native", "vision",
               "learnlm", "gemma", "robotics", "computer-use")

_LOCK = threading.Lock()
_COOLDOWN = {}    # "provider:model" -> unix time when it can be used again
_SEMAPHORES = {}


def reset_health():
    """Forget all cooldowns (used by tests)."""
    with _LOCK:
        _COOLDOWN.clear()


def _semaphore(slot: str) -> threading.Semaphore:
    with _LOCK:
        return _SEMAPHORES.setdefault(slot, threading.Semaphore(PER_SLOT_CONCURRENCY))


def _cooling_until(slot: str) -> float:
    with _LOCK:
        return _COOLDOWN.get(slot, 0.0)


def _retry_after_seconds(message: str):
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)(ms|s)", message)
    if m:
        hours, minutes, value, unit = m.groups()
        secs = float(value) / (1000 if unit == "ms" else 1)
        return secs + 60 * int(minutes or 0) + 3600 * int(hours or 0)
    m = re.search(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", message, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _is_rate_limit(message: str) -> bool:
    text = message.lower()
    return any(w in text for w in ("429", "rate limit", "rate_limit", "resource_exhausted", "quota"))


def _cool_down(slot: str, message: str):
    text = message.lower()
    if "limit: 0" in text or "per day" in text or "perday" in text or "(tpd)" in text or "(rpd)" in text:
        seconds = PARKED_SECONDS
    else:
        seconds = _retry_after_seconds(message) or 30
    with _LOCK:
        _COOLDOWN[slot] = max(_COOLDOWN.get(slot, 0.0), time.time() + seconds + 0.5)


# ---------------- Provider setup (cached, runs on the main thread) ----------------

@st.cache_resource(show_spinner=False)
def _groq_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"], max_retries=0, timeout=CALL_TIMEOUT_SECONDS)


@st.cache_resource(show_spinner=False)
def _groq_models() -> list:
    models = _groq_client().models.list()
    ids = [m.id for m in (getattr(models, "data", None) or [])]
    chat = [i for i in ids if not any(w in i.lower() for w in GROQ_SKIP)]

    def rank(model_id):
        n = model_id.lower()
        return next((i for i, pref in enumerate(GROQ_PREFERRED) if pref in n), len(GROQ_PREFERRED))

    ordered = sorted(chat, key=rank)
    override = st.secrets.get("GROQ_MODEL")
    if override:
        ordered = [override] + [m for m in ordered if m != override]
    if not ordered:
        raise RuntimeError("No Groq chat models found")
    return ordered[:MODELS_PER_PROVIDER]


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
    """Prefer stable Flash models (generous free tier), then Flash-Lite, newest first; Pro last."""
    n = name.lower()
    version = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
    return (
        "flash" in n and "lite" not in n,
        not any(w in n for w in ("preview", "exp", "latest")),
        "flash" in n,
        float(version.group(1)) if version else 0.0,
    )


@st.cache_resource(show_spinner=False)
def _gemini_models() -> list:
    names = []
    for m in _gemini_client().models.list():
        name = getattr(m, "name", "") or ""
        actions = getattr(m, "supported_actions", None) or []
        if "gemini" not in name.lower() or any(w in name.lower() for w in GEMINI_SKIP):
            continue
        if actions and "generateContent" not in actions:
            continue
        names.append(name)
    ordered = sorted(names, key=_gemini_rank, reverse=True)
    override = st.secrets.get("GEMINI_MODEL")
    if override:
        ordered = [override] + [m for m in ordered if m != override]
    if not ordered:
        raise RuntimeError("No Gemini text models found")
    return ordered[:MODELS_PER_PROVIDER]


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
        kwargs.pop("reasoning_effort")
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
_SETUP = {"groq": (_groq_client, _groq_models), "gemini": (_gemini_client, _gemini_models)}


class LLM:
    def __init__(self, mode: str = "auto"):
        self.mode = mode
        self.clients, self.setup_errors, self.slots = {}, {}, []
        providers = list(REAL_PROVIDERS)
        if mode in REAL_PROVIDERS:
            providers = [mode] + [p for p in providers if p != mode]
        for provider in providers:
            get_client, get_models = _SETUP[provider]
            try:
                self.clients[provider] = get_client()
                self.slots += [(provider, m) for m in get_models()]
            except Exception as e:
                self.setup_errors[provider] = f"{type(e).__name__}: {e}"
        if not self.slots:
            raise RuntimeError(f"No AI model available. Details: {self.setup_errors}")
        if mode == "auto":  # interleave providers so the work is shared from the start
            groq = [s for s in self.slots if s[0] == "groq"]
            gem = [s for s in self.slots if s[0] == "gemini"]
            mixed = []
            for i in range(max(len(groq), len(gem))):
                mixed += groq[i:i + 1] + gem[i:i + 1]
            self.slots = mixed

    # Kept for older callers: the providers that have at least one model
    @property
    def order(self) -> list:
        return list(dict.fromkeys(p for p, _ in self.slots))

    @property
    def ready(self) -> dict:
        return {p: (self.clients[p], next(m for q, m in self.slots if q == p)) for p in self.order}

    def model_name(self, provider: str) -> str:
        return next((m for p, m in self.slots if p == provider), "unavailable")

    @staticmethod
    def key(slot) -> str:
        return f"{slot[0]}:{slot[1]}"

    def healthy_slots(self) -> list:
        now = time.time()
        return [s for s in self.slots if _cooling_until(self.key(s)) <= now] or list(self.slots)

    def preferred_for(self, index: int):
        """Spread sections across healthy slots (in Groq-first / Gemini-first modes, that provider's slots)."""
        healthy = self.healthy_slots()
        if self.mode in REAL_PROVIDERS:
            healthy = [s for s in healthy if s[0] == self.mode] or healthy
        return self.key(healthy[index % len(healthy)])

    def _ordered(self, prefer, avoid_model):
        slots = list(self.slots)
        if prefer:
            first = [s for s in slots if self.key(s) == prefer] or [s for s in slots if s[0] == prefer]
            if first:
                slots = [first[0]] + [s for s in slots if s != first[0]]
        if avoid_model:
            slots = [s for s in slots if s[1] != avoid_model] + [s for s in slots if s[1] == avoid_model]
        return slots

    def chat(self, system: str, user: str, temperature: float = 0.3, max_tokens: int = 1000,
             prefer: str = None, avoid_model: str = None) -> dict:
        """Returns {"text", "provider", "model", "fallback", "errors"}."""
        order = self._ordered(prefer, avoid_model)
        attempts, errors = {}, []
        started = time.time()
        while True:
            now = time.time()
            usable = [s for s in order if attempts.get(self.key(s), 0) < MAX_ATTEMPTS_PER_SLOT
                      and _cooling_until(self.key(s)) <= now]
            if not usable:
                waiting = [_cooling_until(self.key(s)) for s in order
                           if attempts.get(self.key(s), 0) < MAX_ATTEMPTS_PER_SLOT]
                if not waiting:
                    break
                wake = min(waiting)
                if wake - now > MAX_WAIT_SECONDS or wake - started > MAX_WAIT_SECONDS * 2:
                    break
                time.sleep(max(0.2, wake - now))
                continue

            slot = usable[0]
            key = self.key(slot)
            attempts[key] = attempts.get(key, 0) + 1
            semaphore = _semaphore(key)
            if not semaphore.acquire(timeout=MAX_WAIT_SECONDS):
                errors.append(f"{key}: busy")
                continue
            try:
                text = _CALLERS[slot[0]](self.clients[slot[0]], slot[1], system, user, temperature, max_tokens)
            except Exception as e:
                message = f"{type(e).__name__}: {e}"
                errors.append(f"{key}: {message[:200]}")
                if _is_rate_limit(message):
                    _cool_down(key, message)
                else:
                    attempts[key] = MAX_ATTEMPTS_PER_SLOT  # not a rate limit: don't retry this slot
                continue
            finally:
                semaphore.release()
            if text:
                return {"text": text, "provider": slot[0], "model": slot[1],
                        "fallback": slot != order[0], "errors": errors}
            errors.append(f"{key}: empty answer")
            attempts[key] = MAX_ATTEMPTS_PER_SLOT
        raise RuntimeError("All AI models failed. " + " | ".join(errors[-4:]))
