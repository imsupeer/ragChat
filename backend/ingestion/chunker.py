from langchain_text_splitters import RecursiveCharacterTextSplitter


def build_text_splitter(
    chunk_size: int = 800, chunk_overlap: int = 200
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )
