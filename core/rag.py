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
    index = VectorStoreIndex.from_documents(
        documents, transformations=[splitter], embed_model=get_embed_model()
    )
    # Fetch extra candidates, then cap chunks per page so one page can't dominate
    candidates = index.as_retriever(similarity_top_k=top_k * 4).retrieve(query)

    picked, count_per_url = [], {}
    for r in candidates:
        url = r.metadata["url"]
        if count_per_url.get(url, 0) >= max_per_source:
            continue
        count_per_url[url] = count_per_url.get(url, 0) + 1
        picked.append({
            "text": r.get_content(),
            "url": url,
            "title": r.metadata["title"],
            "score": round(r.score or 0, 3),
        })
        if len(picked) == top_k:
            break
    return picked
