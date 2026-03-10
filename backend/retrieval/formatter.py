from typing import List
from langchain_core.documents import Document


def format_retrieved_chunks(docs: List[Document]) -> str:
    sections = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "n/a")
        chunk_index = doc.metadata.get("chunk_index", "n/a")

        header = f"[SOURCE: {source} | page={page} | chunk={chunk_index}]"
        sections.append(f"{header}\n{doc.page_content}")

    return "\n\n".join(sections)


def serialize_sources(docs: List[Document]) -> list[dict]:
    sources = []
    for doc in docs:
        sources.append(
            {
                "source": doc.metadata.get("source", "unknown"),
                "page": doc.metadata.get("page"),
                "chunk_index": doc.metadata.get("chunk_index"),
                "preview": doc.page_content[:280],
            }
        )
    return sources
