"""Chunking, embedding and retrieval with LlamaIndex + FastEmbed."""
import streamlit as st
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.fastembed import FastEmbedEmbedding


@st.cache_resource(show_spinner=False)
def get_embed_model():
    # Small, free embedding model that runs inside the app (no API needed)
    return FastEmbedEmbedding(model_name="BAAI/bge-small-en-v1.5")


def retrieve(pages: list[dict], query: str, top_k: int = 6) -> list[dict]:
    documents = [
        Document(
            text=p["text"],
            metadata={"url": p["url"], "title": p["title"]},
            excluded_embed_metadata_keys=["url"],
        )
        for p in pages
    ]
    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=64)
    index = VectorStoreIndex.from_documents(
        documents, transformations=[splitter], embed_model=get_embed_model()
    )
    results = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    return [
        {
            "text": r.get_content(),
            "url": r.metadata["url"],
            "title": r.metadata["title"],
            "score": round(r.score or 0, 3),
        }
        for r in results
    ]
