"""The candidate's profile: experience level, interview round, job description, resume.

Privacy: the JD and resume live only in memory for one report. They are never
written to disk, never sent to the web search, and reports that use them are
never saved to the shared report cache.
"""
import io
import re

from pypdf import PdfReader

LEVELS = ["Not specified", "Intern", "Fresher", "1-3 years", "3-6 years", "6+ years"]
ROUNDS = ["All rounds", "Online assessment", "Technical", "Case study", "HR", "Managerial"]

# How each level is phrased in web searches (empty = add nothing)
LEVEL_SEARCH_WORDS = {
    "Not specified": "", "Intern": "intern", "Fresher": "fresher",
    "1-3 years": "", "3-6 years": "experienced", "6+ years": "senior",
}

MAX_RESUME_PAGES = 5
MAX_JD_WORDS = 1500        # longer pastes are trimmed
RESUME_PROMPT_WORDS = 800  # what the writer actually sees (free-tier token limits)
JD_PROMPT_WORDS = 700
JD_PLANNER_WORDS = 250     # the planner only needs the gist of the JD


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _first_words(text: str, n: int) -> str:
    words = (text or "").split()
    return " ".join(words[:n]) + (" ..." if len(words) > n else "")


def read_resume(file_bytes: bytes):
    """Returns (text, warning). Text is empty if the PDF can't be read."""
    if not file_bytes:
        return "", None
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            return "", "Your resume PDF is password-protected, so it was skipped."
        pages = reader.pages[:MAX_RESUME_PAGES]
        text = _clean(" ".join((page.extract_text() or "") for page in pages))
    except Exception:
        return "", "Couldn't read your resume PDF, so it was skipped."
    if len(text.split()) < 30:
        return "", ("Couldn't find text in your resume (it may be a scanned image), "
                    "so it was skipped. Try a PDF exported from Word or Google Docs.")
    note = (f"Only the first {MAX_RESUME_PAGES} pages of your resume were used."
            if len(reader.pages) > MAX_RESUME_PAGES else None)
    return text, note


def make_profile(level: str = "Not specified", round_type: str = "All rounds",
                 jd: str = "", resume: str = "") -> dict:
    jd = _first_words(_clean(jd), MAX_JD_WORDS)
    return {
        "level": level if level in LEVELS else "Not specified",
        "round": round_type if round_type in ROUNDS else "All rounds",
        "jd": jd,
        "resume": _clean(resume),
    }


def is_personal(profile: dict) -> bool:
    """True if the report uses private material (JD or resume)."""
    return bool(profile.get("jd") or profile.get("resume"))


def level_search_words(profile: dict) -> str:
    return LEVEL_SEARCH_WORDS.get(profile.get("level", ""), "")


def jd_for_planner(profile: dict) -> str:
    return _first_words(profile.get("jd", ""), JD_PLANNER_WORDS)


def profile_block(profile: dict, use_jd: bool, use_resume: bool) -> str:
    """The candidate details a section writer sees. Empty string if nothing applies."""
    lines = []
    if profile.get("level") and profile["level"] != "Not specified":
        lines.append(f"Experience level: {profile['level']}")
    if profile.get("round") and profile["round"] != "All rounds":
        lines.append(f"Interview round to focus on: {profile['round']}")
    if use_jd and profile.get("jd"):
        lines.append(f"Job description (from the candidate):\n{_first_words(profile['jd'], JD_PROMPT_WORDS)}")
    if use_resume and profile.get("resume"):
        lines.append(f"Candidate's resume:\n{_first_words(profile['resume'], RESUME_PROMPT_WORDS)}")
    return "\n\n".join(lines)
