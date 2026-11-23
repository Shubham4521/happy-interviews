"""Writes the 6 report sections from retrieved chunks, in parallel.

Every point is labeled:
  🌐 = based on a web source (with a citation like [3])
  💼 = based on the candidate's own resume or job description
  💡 = AI suggestion (no citation)
A guardrail removes any citation number the model invents that wasn't in that
section's sources. Sections that fail (e.g. both free tiers busy at once) are
retried once, a few seconds later, one at a time.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.profile import profile_block
from core.sections import SECTIONS

WEAK_SOURCE_THRESHOLD = 3  # fewer relevant chunks than this = "limited information"
MAX_PARALLEL_SECTIONS = 6  # all at once; Auto mode splits them across two providers
RETRY_DELAY_SECONDS = 4

BASE_SYSTEM = """You write ONE section of an interview prep report.
Labeling rules (very important):
- A point based on the sources starts with 🌐 and ends with its citation(s), like [2] or [1][3].
- A point based on the candidate's own resume or job description starts with 💼 and has NO citation.
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
describe the typical process for this role and level at similar companies, with every point
marked 💡. If an interview round focus is given, add tips for that round. Under 300 words.""",

    "likely_questions": """Use these subheadings: ### Technical (5-7 questions), ### Behavioral
(3-5 questions), ### Company-specific (3-4 questions). Write each as an actual question.
Mark it 🌐 with a citation if candidates reported it in the sources, otherwise 💡.
Tailor technical questions to the {role} role and match their difficulty to the experience
level if given. If an interview round focus is given, most questions should fit that round.
If a job description is given, include questions on its key skills, marked 💼.""",

    "talking_points": """Give 3-5 talking points. For each: a bullet starting with 🌐 that summarizes
one recent development in bold, ending with its citation; then an indented sub-bullet
starting with 💡 **How to use it:** and one sentence on how to weave it into an answer.
If a resume is given, end with a ### Connect your experience subheading: 2-3 bullets starting
with 💼 that link specific projects or skills from the resume to the company's work.""",

    "questions_to_ask": """Give 5 thoughtful questions the candidate can ask the interviewer. Each is
a bullet starting with 💡 and the question in bold, followed by an indented sub-bullet
**Why it works:** that references a sourced fact (🌐 with citation) where possible.
Avoid questions a quick web search would answer. Suit them to the experience level if given.""",

    "prep_checklist": """Write a checklist using "- [ ] " items, grouped under ### Technical skills,
### Company knowledge, ### Behavioral prep, with 4-6 items per group. Right after "- [ ] ",
put 🌐 for items based on the sources (with a citation), 💼 for items from the job description
or resume, or 💡 for general advice. If a job description is given, cover each major skill it
lists. If both a resume and a job description are given, add a ### Gaps to close group with
💼 items for JD skills the resume doesn't show. Match depth to the experience level if given.""",
}

# Which private profile parts each section sees (level and round always apply)
SECTION_PROFILE_USE = {
    "company_snapshot": {"jd": False, "resume": False},
    "interview_process": {"jd": False, "resume": False},
    "likely_questions": {"jd": True, "resume": True},
    "talking_points": {"jd": False, "resume": True},
    "questions_to_ask": {"jd": True, "resume": False},
    "prep_checklist": {"jd": True, "resume": True},
}

WEAK_NOTE = """Very few relevant sources were found. Start the section with exactly this line:
> ⚠️ Limited public information found. Most points below are AI suggestions.
Then mark points 💡 (or 💼) unless a source clearly supports them."""

CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
ODD_CITATION = re.compile(r"[\[【](\d+)(?:†[^\]】]*)?[\]】]")  # e.g. 【3†source】 or [3†L1-L4]


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
    """Guardrail on the model's citations:
    1. normalizes unusual formats like 【3†source】 to [3],
    2. removes citation numbers that weren't in this section's sources,
    3. downgrades a Source-tagged line with no citation left to an AI tip, so the
       Source label never promises a link the reader can't open.
    Returns (text, removed_numbers, downgraded_lines)."""
    removed = []

    def fix(match):
        nums = [int(n) for n in re.split(r"\s*,\s*", match.group(1))]
        keep = [n for n in nums if n in valid_nums]
        removed.extend(n for n in nums if n not in valid_nums)
        return "".join(f"[{n}]" for n in keep)

    text = ODD_CITATION.sub(lambda m: f"[{m.group(1)}]", text)
    text = CITATION.sub(fix, text)
    lines, downgraded = [], 0
    for line in text.splitlines():
        if "🌐" in line and not CITATION.search(line):
            line = line.replace("🌐", "💡")
            downgraded += 1
        lines.append(line)
    return "\n".join(lines), removed, downgraded


def write_section(llm, key: str, company: str, role: str, location: str, chunks: list,
                  prefer: str = None, profile: dict = None) -> dict:
    started = time.perf_counter()
    cfg = SECTIONS[key]
    weak = len(chunks) < WEAK_SOURCE_THRESHOLD
    context = "\n\n".join(f"[{c['num']}] {c['text']}" for c in chunks) or "(no relevant sources found)"
    use = SECTION_PROFILE_USE[key]
    candidate = profile_block(profile or {}, use_jd=use["jd"], use_resume=use["resume"])
    user = f"""Candidate: preparing for a {role} interview at {company} ({location}).
{candidate}

Section to write: {cfg['title']}

Numbered sources (some may be irrelevant; use only what is relevant):
{context}

Instructions:
{SECTION_INSTRUCTIONS[key].format(role=role)}
{WEAK_NOTE if weak else ''}"""

    result = {"key": key, "title": cfg["title"], "weak": weak, "provider": None,
              "model": None, "fallback": False, "removed_citations": [], "downgraded": 0,
              "error": None, "retried": False}
    try:
        answer = llm.chat(BASE_SYSTEM, user, max_tokens=1000, prefer=prefer)
        text, removed, downgraded = clean_citations(answer["text"], {c["num"] for c in chunks})
        result.update(text=text, provider=answer["provider"], model=answer["model"],
                      fallback=answer["fallback"], removed_citations=removed, downgraded=downgraded,
                      provider_errors=answer["errors"])
    except Exception as e:
        result.update(text="⚠️ Couldn't generate this section right now. Please try again in a minute.",
                      error=f"{type(e).__name__}: {e}")
    result["seconds"] = round(time.perf_counter() - started, 1)
    return result


def write_report(llm, company: str, role: str, location: str, section_chunks: dict,
                 profile: dict = None):
    """Writes all sections in parallel, then retries any failures once, one at a time.
    Yields each result as soon as it's finished (a retried section is yielded again)."""
    failed = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SECTIONS) as pool:
        futures = {
            pool.submit(write_section, llm, key, company, role, location,
                        section_chunks.get(key) or [], llm.preferred_for(i), profile): key
            for i, key in enumerate(SECTIONS)
        }
        for future in as_completed(futures):
            result = future.result()
            if result["error"]:
                failed.append(result)
            yield result

    keys = list(SECTIONS)
    for i, first_try in enumerate(failed):
        time.sleep(RETRY_DELAY_SECONDS if i == 0 else 1)  # let rate limits cool down
        # start the retry on a different model than the first attempt
        result = write_section(llm, first_try["key"], company, role, location,
                               section_chunks.get(first_try["key"]) or [],
                               prefer=llm.preferred_for(keys.index(first_try["key"]) + 1), profile=profile)
        result["retried"] = True
        yield result
