"""The AI judge.

1. Citation accuracy: for every Source-tagged claim, the judge reads the claim
   next to the text of the page(s) it cites and labels it supported, partial,
   or unsupported.
2. Retrieval relevance: for every passage picked for a section, the judge says
   whether it's useful for writing that section.

Cross-model judging: each claim is judged by a different model than the one
that wrote it, so no model grades its own writing. If only that model is
available, the result is marked "self_judged".
"""
import json
import re

CITATION = re.compile(r"\[(\d+)\]")
CLAIMS_PER_CALL = 10
EVIDENCE_CHARS_PER_CLAIM = 1400
PASSAGE_CHARS = 500

CLAIM_JUDGE_SYSTEM = """You are a strict fact-checker. For each claim, compare it ONLY with its evidence.
- "supported": the evidence states the claim (paraphrasing is fine).
- "partial": the main point is in the evidence, but a detail (number, date, name) is missing or different.
- "unsupported": the evidence does not state the claim, or contradicts it.
Return ONLY JSON: {"verdicts": [{"id": <id>, "verdict": "supported|partial|unsupported", "reason": "<max 12 words>"}]}"""

RELEVANCE_JUDGE_SYSTEM = """You judge search results for an interview prep report.
For each passage, answer 1 if it contains information useful for writing that section
for this company and role, otherwise 0. Return ONLY JSON, for example:
{"S1": [1, 0, 1], "S2": [0, 1]}"""

VERDICTS = ("supported", "partial", "unsupported")


def parse_json(text: str):
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _plain(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*+]\s+(?:\[[ xX]?\]\s+)?|\d+[.)]\s+)", "", line)
    line = line.replace("**", "").replace("🌐", "").replace("💼", "").replace("💡", "")
    return " ".join(line.split())


def extract_claims(section_text: str) -> tuple:
    """Returns (claims, uncited). A claim is a line tagged 🌐 with at least one citation."""
    claims, uncited = [], 0
    for line in (section_text or "").splitlines():
        if "🌐" not in line:
            continue
        nums = sorted({int(n) for n in CITATION.findall(line)})
        text = CITATION.sub("", _plain(line)).strip()
        if not text:
            continue
        if nums:
            claims.append({"claim": text, "nums": nums})
        else:
            uncited += 1
    return claims, uncited


def evidence_for(nums: list, chunks: list) -> str:
    parts = [f"[{c['num']}] {c['text']}" for c in chunks if c.get("num") in nums]
    return "\n".join(parts)[:EVIDENCE_CHARS_PER_CLAIM]


def judge_claims(llm, items: list, writer_model: str) -> list:
    """items: [{"id", "claim", "evidence"}]. Adds "verdict", "reason", "judge", "self_judged"."""
    for start in range(0, len(items), CLAIMS_PER_CALL):
        batch = items[start:start + CLAIMS_PER_CALL]
        listing = "\n\n".join(f"Claim {it['id']}: {it['claim']}\nEvidence:\n{it['evidence']}" for it in batch)
        try:
            answer = llm.chat(CLAIM_JUDGE_SYSTEM, listing, temperature=0.0, max_tokens=1200,
                              avoid_model=writer_model)
            data = parse_json(answer["text"]) or {}
            by_id = {int(v.get("id")): v for v in data.get("verdicts") or []
                     if isinstance(v, dict) and str(v.get("id", "")).isdigit()}
            judge = answer["model"]
        except Exception:
            by_id, judge = {}, None
        for it in batch:
            v = by_id.get(it["id"], {})
            verdict = str(v.get("verdict", "")).lower().strip()
            it["verdict"] = verdict if verdict in VERDICTS else "judge_failed"
            it["reason"] = str(v.get("reason", ""))[:120]
            it["judge"] = judge
            it["self_judged"] = judge == writer_model
    return items


def judge_relevance(llm, company: str, role: str, section_payload: list) -> dict:
    """section_payload: [{"sid", "title", "passages": [text, ...]}] -> {"S1": [1, 0, ...], ...} or {}."""
    blocks = []
    for s in section_payload:
        passages = "\n".join(f"  ({i + 1}) {p[:PASSAGE_CHARS]}" for i, p in enumerate(s["passages"]))
        blocks.append(f"{s['sid']}: section \"{s['title']}\"\n{passages}")
    user = f"Company: {company}. Role: {role}.\n\n" + "\n\n".join(blocks)
    try:
        answer = llm.chat(RELEVANCE_JUDGE_SYSTEM, user, temperature=0.0, max_tokens=800, prefer="gemini")
        data = parse_json(answer["text"]) or {}
    except Exception:
        return {}
    clean = {}
    for s in section_payload:
        values = data.get(s["sid"])
        if isinstance(values, list) and len(values) == len(s["passages"]):
            clean[s["sid"]] = [1 if str(v).strip() in ("1", "True", "true", "yes") else 0 for v in values]
    return clean
