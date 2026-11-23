"""Chunking, embedding, per-section retrieval and reranking.

Built directly on FastEmbed + NumPy, so every step is easy to explain:
  1. split each page into overlapping word windows (chunks)
  2. embed all chunks ONCE (bi-encoder: one vector per chunk)
  3. for each report section: score chunks by cosine similarity to that
     section's query, with a small boost for chunks from matching topics
  4. rerank the top candidates with a cross-encoder (reads query + chunk
     together, so it's more precise but slower, hence only on the top few)
  5. keep the best chunks, max 2 per page for source diversity
"""
import numpy as np
import streamlit as st
from fastembed import TextEmbedding

CHUNK_WORDS = 220      # about 300 tokens per chunk
OVERLAP_WORDS = 40     # overlap so sentences cut at a boundary aren't lost
MIN_CHUNK_WORDS = 40
TOPIC_BOOST = 0.05     # nudge chunks from searches meant for this section
RERANK_CANDIDATES = 20
EMBED_BATCH_SIZE = 16  # small batches keep memory low on free hosting
RERANK_BATCH_SIZE = 8
MAX_CHUNKS_PER_PAGE = 6
MAX_TOTAL_CHUNKS = 180


@st.cache_resource(show_spinner=False)
def get_embedder():
    return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


@st.cache_resource(show_spinner=False)
def get_reranker():
    """Returns the cross-encoder, or None if it can't load (we then skip reranking)."""
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        return TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
    except Exception:
        return None


def chunk_text(text: str) -> list:
    words = (text or "").split()
    if not words:
        return []
    step = CHUNK_WORDS - OVERLAP_WORDS
    chunks = []
    for start in range(0, len(words), step):
        piece = words[start:start + CHUNK_WORDS]
        if len(piece) < MIN_CHUNK_WORDS and chunks:
            break  # tiny leftover tail is already covered by the overlap
        chunks.append(" ".join(piece))
        if start + CHUNK_WORDS >= len(words):
            break
    return chunks


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def build_index(pages: list) -> dict:
    """Chunks every page and embeds all chunks once. Reused by every section."""
    chunks = []
    for p in pages or []:
        for piece in chunk_text(p.get("text"))[:MAX_CHUNKS_PER_PAGE]:
            chunks.append({
                "text": piece,
                "url": p["url"],
                "title": p["title"],
                "topics": p.get("topics") or [],
            })
    chunks = chunks[:MAX_TOTAL_CHUNKS]
    if not chunks:
        return {"chunks": [], "vectors": np.zeros((0, 1))}
    vectors = np.array(list(get_embedder().passage_embed(
        [c["text"] for c in chunks], batch_size=EMBED_BATCH_SIZE)))
    return {"chunks": chunks, "vectors": _normalize(vectors)}


def _rerank(query: str, candidates: list) -> list:
    reranker = get_reranker()
    if reranker is None or not candidates:
        return candidates
    try:
        scores = list(reranker.rerank(query, [c["text"] for c in candidates],
                                      batch_size=RERANK_BATCH_SIZE))
        if len(scores) != len(candidates):
            return candidates
        for c, s in zip(candidates, scores):
            c["rerank_score"] = round(float(s), 3)
        return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
    except Exception:
        return candidates  # reranking is a bonus, never a point of failure


def retrieve_for_section(index: dict, query: str, topics: list,
                         top_k: int = 6, max_per_source: int = 2,
                         use_rerank: bool = True) -> list:
    chunks, vectors = index["chunks"], index["vectors"]
    if not chunks:
        return []

    query_vec = _normalize(np.array(list(get_embedder().query_embed([query])))[0])
    scores = vectors @ query_vec
    boost = np.array([TOPIC_BOOST if set(c["topics"]) & set(topics) else 0.0 for c in chunks])
    scores = scores + boost

    # Take the best candidates (with a looser per-page cap), then rerank them
    candidates, per_url = [], {}
    for i in np.argsort(-scores):
        c = chunks[int(i)]
        if per_url.get(c["url"], 0) >= max_per_source + 1:
            continue
        per_url[c["url"]] = per_url.get(c["url"], 0) + 1
        candidates.append({**c, "score": round(float(scores[i]), 3)})
        if len(candidates) == RERANK_CANDIDATES:
            break
    if use_rerank:
        candidates = _rerank(query, candidates)

    picked, per_url = [], {}
    for c in candidates:
        if per_url.get(c["url"], 0) >= max_per_source:
            continue
        per_url[c["url"]] = per_url.get(c["url"], 0) + 1
        picked.append(c)
        if len(picked) == top_k:
            break
    return picked


def reranker_available() -> bool:
    return get_reranker() is not None
