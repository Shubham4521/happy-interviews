"""Chunking, embedding and retrieval with LlamaIndex + FastEmbed."""
import os

import nltk

# --- NLTK setup: use a private folder that only this app can write to ---
NLTK_DIR = os.path.join(os.path.expanduser("~"), ".happy_nltk_data")
os.makedirs(NLTK_DIR, mode=0o700, exist_ok=True)
os.environ["NLTK_DATA"] = NLTK_DIR          # LlamaIndex reads this
nltk.data.path.insert(0, NLTK_DIR)          # NLTK checks this folder first
for package, resource in [("stopwords", "corpora/stopwords"),
                          ("punkt_tab", "tokenizers/punkt_tab")]:
    try:
        nltk.data.find(resource)
    except LookupError:
        nltk.download(package, download_dir=NLTK_DIR, quiet=True)
# -------------------------------------------------------------------------

import streamlit as st  # noqa: E402
from llama_index.core import Document, VectorStoreIndex  # noqa: E402
from llama_index.core.node_parser import SentenceSplitter  # noqa: E402
from llama_index.embeddings.fastembed import FastEmbedEmbedding  # noqa: E402


@st.cache_resource(show_spinner=False)
def get_embed_model():
    # Small, free embedding model that runs inside the app (no API needed)
    return FastEmbedEmbedding(model_name="BAAI/bge-small-en-v1.5")


def retrieve(pages: list[dict], query: str, top_k: int = 6,
             max_per_source: int = 2) -> list[dict]:
    documents = [
        Document(
            text=p["text"],
            metadata={"url": p["url"], "title": p["title"]},
            excluded_embed_metadata_keys=["url"],
        )
        for p in pages
    ]
    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=64)
    index = VectorStoreIndex.from_documents(documents, transformations=[splitter], embed_model=get_embed_model())
    # Fetch extra candidates, then cap chunks per page so one page can't dominate
    candidates = index.as_retriever(similarity_top_k=top_k * 4).retrieve(query)
