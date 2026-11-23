"""Chunking, embedding and retrieval.

Built directly on FastEmbed + NumPy (no LlamaIndex), so there are no hidden
NLTK downloads and every step is easy to explain:
  1. split each page into overlapping word windows (chunks)
  2. turn chunks and the query into vectors (embeddings)
  3. rank chunks by cosine similarity to the query
  4. keep the top results, max 2 per page for source diversity
"""
import numpy as np
import streamlit as st
from fastembed import TextEmbedding

CHUNK_WORDS = 220    # about 300 tokens per chunk
OVERLAP_WORDS = 40   # overlap so sentences cut at a boundary aren't lost
MIN_CHUNK_WORDS = 40


@st.cache_resource(show_spinner=False)
def get_embedder():
    # Small, free embedding model that runs inside the app (no API needed)
    return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


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


def rank_chunks(chunk_vecs: np.ndarray, query_vec: np.ndarray) -> np.ndarray:
    """Cosine similarity of every chunk to the query."""
    return _normalize(chunk_vecs) @ _normalize(query_vec.reshape(1, -1))[0]


def pick_diverse(chunks: list, scores: np.ndarray, top_k: int, max_per_source: int) -> list:
    picked, count_per_url = [], {}
    for i in np.argsort(-scores):
        c = chunks[int(i)]
        if count_per_url.get(c["url"], 0) >= max_per_source:
            continue
        count_per_url[c["url"]] = count_per_url.get(c["url"], 0) + 1
        picked.append({**c, "score": round(float(scores[i]), 3)})
        if len(picked) == top_k:
            break
    return picked


def retrieve(pages: list, query: str, top_k: int = 6, max_per_source: int = 2) -> list:
    chunks = []
    for p in pages or []:
        for piece in chunk_text(p.get("text")):
            chunks.append({"text": piece, "url": p["url"], "title": p["title"]})
    if not chunks:
        return []

    embedder = get_embedder()
    chunk_vecs = np.array(list(embedder.passage_embed([c["text"] for c in chunks])))
    query_vec = np.array(list(embedder.query_embed([query])))[0]
    scores = rank_chunks(chunk_vecs, query_vec)
    return pick_diverse(chunks, scores, top_k, max_per_source)
