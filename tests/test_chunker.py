from backend.ingestion.chunker import build_text_splitter
from langchain_core.documents import Document


def test_chunker_splits_text():
    splitter = build_text_splitter(chunk_size=50, chunk_overlap=10)
    docs = [Document(page_content="A" * 140, metadata={})]
    chunks = splitter.split_documents(docs)

    assert len(chunks) > 1
