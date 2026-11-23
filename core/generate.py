"""Writes the 6 report sections from retrieved chunks, in parallel.

Each section gets its own prompt, and every point is labeled:
  🌐 = based on a web source (with a citation like [3])
  💡 = AI suggestion (no citation)
A guardrail removes any citation number the model invents that wasn't in that
section's sources, so every [n] in the report points to a real, provided page.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.sections import SECTIONS

WEAK_SOURCE_THRESHOLD = 3  # fewer relevant chunks than this = "limited information"
MAX_PARALLEL_SECTIONS = 6  # all at once; Auto mode splits them across two providers

BASE_SYSTEM = """You write ONE section of an interview prep report.
Labeling rules (very important):
- A point based on the sources starts with 🌐 and ends with its citation(s), like [2] or [1][3].
- A point that is your own advice or general knowledge starts with 💡 and has NO citation.
- Company-specific facts (numbers, dates, names, interview rounds) must come from the
  sources with a citation. Never invent them.
- Only cite source numbers that appear in the provided sources.
- Output markdown only: no preamble, no closing remarks, no top-level title."""

SECTION_INSTRUCTIONS = {
    "company_snapshot": """Use these subheadings: ### What they do, ### Business and scale,
### Recent news, ### Culture and values. 2-4 bullet points under each, mostly 🌐.
Under 300 words.""",

    "interview_process": """Use these subheadings: ### Rounds (a numbered list; for each round give
its format and what it tests), ### Duration and difficulty, ### Tips from candidates.
Use 🌐 for anything reported in the sources. If the sources don't describe the process,
describe the typical process for this role at similar companies, with every point marked 💡.
Under 300 words.""",

    "likely_questions": """Use these subheadings: ### Technical (5-7 questions), ### Behavioral
(3-5 questions), ### Company-specific (3-4 questions). Write each as an actual question.
Mark it 🌐 with a citation if candidates reported it in the sources, otherwise 💡.
Tailor technical questions to the {role} role.""",

    "talking_points": """Give 3-5 talking points. For each: a bullet starting with 🌐 that summarizes
one recent development in bold, ending with its citation; then an indented sub-bullet
starting with 💡 **How to use it:** and one sentence on how to weave it into an answer.""",

    "questions_to_ask": """Give 5 thoughtful questions the candidate can ask the interviewer. Each is
a bullet starting with 💡 and the question in bold, followed by an indented sub-bullet
**Why it works:** that references a sourced fact (🌐 with citation) where possible.
Avoid questions a quick web search would answer.""",

    "prep_checklist": """Write a checklist using "- [ ] " items, grouped under ### Technical skills,
### Company knowledge, ### Behavioral prep, with 4-6 items per group. Right after "- [ ] ",
put 🌐 for items based on the sources (with a citation) or 💡 for general advice.""",
}

WEAK_NOTE = """Very few relevant sources were found. Start the section with exactly this line:
> ⚠️ Limited public information found. Most points below are AI suggestions.
Then mark points 💡 unless a source clearly supports them."""

CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def assign_source_numbers(section_chunks: dict) -> list:
    """One numbering for the whole report: the same page keeps the same number in every section."""
    sources, url_to_num = [], {}
    for key in SECTIONS:
        for c in section_chunks.get(key) or []:
            if c["url"] not in url_to_num:
                url_to_num[c["url"]] = len(sources) + 1
                sources.append({"num": url_to_num[c["url"]], "url": c["url"], "title": c["title"]})
            c["num"] = url_to_num[c["url"]]
    return sources


def clean_citations(text: str, valid_nums: set):
    """Removes citation numbers that weren't in this section's sources. Returns (text, removed)."""
    removed = []

    def fix(match):
        nums = [int(n) for n in re.split(r"\s*,\s*", match.group(1))]
        keep = [n for n in nums if n in valid_nums]
        removed.extend(n for n in nums if n not in valid_nums)
        return "".join(f"[{n}]" for n in keep)

    return CITATION.sub(fix, text), removed


def write_section(llm, key: str, company: str, role: str, location: str, chunks: list,
                  prefer: str = None) -> dict:
    started = time.perf_counter()
    cfg = SECTIONS[key]
    weak = len(chunks) < WEAK_SOURCE_THRESHOLD
    context = "\n\n".join(f"[{c['num']}] {c['text']}" for c in chunks) or "(no relevant sources found)"
    user = f"""Candidate: preparing for a {role} interview at {company} ({location}).
Section to write: {cfg['title']}

Numbered sources (some may be irrelevant; use only what is relevant):
{context}

Instructions:
{SECTION_INSTRUCTIONS[key].format(role=role)}
{WEAK_NOTE if weak else ''}"""

    result = {"key": key, "title": cfg["title"], "weak": weak, "provider": None,
              "model": None, "fallback": False, "removed_citations": [], "error": None}
    try:
        answer = llm.chat(BASE_SYSTEM, user, max_tokens=1500, prefer=prefer)
        text, removed = clean_citations(answer["text"], {c["num"] for c in chunks})
        result.update(text=text, provider=answer["provider"], model=answer["model"],
                      fallback=answer["fallback"], removed_citations=removed,
                      provider_errors=answer["errors"])
    except Exception as e:
        result.update(text="⚠️ Couldn't generate this section right now. Please try again in a minute.",
                      error=f"{type(e).__name__}: {e}")
    result["seconds"] = round(time.perf_counter() - started, 1)
    return result


def write_report(llm, company: str, role: str, location: str, section_chunks: dict):
    """Writes all sections in parallel. Yields each result as soon as it's finished."""
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SECTIONS) as pool:
        futures = [
            pool.submit(write_section, llm, key, company, role, location,
                        section_chunks.get(key) or [], llm.preferred_for(i))
            for i, key in enumerate(SECTIONS)
        ]
        for future in as_completed(futures):
            yield future.result()
