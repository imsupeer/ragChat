import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
NUMBERED_HEADING_RE = re.compile(
    r"^\s*((\d+(?:\.\d+)*)|([IVXLC]+))[.)]?\s+[A-Z].{0,100}$"
)


@dataclass
class SectionSegment:
    text: str
    metadata: dict


def build_text_splitter(
    chunk_size: int = 800, chunk_overlap: int = 200
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )


def chunk_documents(
    docs: List[Document],
    source_path: str,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> List[Document]:
    splitter = build_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    suffix = Path(source_path).suffix.lower()

    if suffix in {".md", ".markdown"}:
        segments = segment_markdown_documents(docs)
    elif suffix == ".pdf":
        segments = segment_pdf_documents(docs)
    else:
        segments = segment_text_documents(docs)

    chunks: List[Document] = []
    for segment in segments:
        segment_doc = Document(
            page_content=segment.text,
            metadata=dict(segment.metadata),
        )
        split_docs = splitter.split_documents([segment_doc])

        for split_doc in split_docs:
            split_doc.page_content = build_section_content(
                text=split_doc.page_content,
                section_path=split_doc.metadata.get("section_path"),
            )

        chunks.extend(split_docs)

    if chunks:
        return chunks

    return splitter.split_documents(docs)


def segment_markdown_documents(docs: List[Document]) -> List[SectionSegment]:
    combined_text = "\n\n".join(
        doc.page_content for doc in docs if doc.page_content.strip()
    )
    if not combined_text.strip():
        return []

    base_metadata = dict(docs[0].metadata or {}) if docs else {}
    lines = combined_text.splitlines()
    heading_stack: list[str] = []
    current_lines: list[str] = []
    segments: List[SectionSegment] = []

    def flush_current_section() -> None:
        text = "\n".join(current_lines).strip()
        if not text:
            return

        section_title = heading_stack[-1] if heading_stack else None
        if section_title and is_heading_only_block(text, section_title):
            return

        section_path = " > ".join(heading_stack) if heading_stack else None
        metadata = dict(base_metadata)
        metadata["section_title"] = section_title or "Document"
        metadata["section_path"] = section_path or "Document"
        segments.append(SectionSegment(text=text, metadata=metadata))

    for line in lines:
        heading_match = MARKDOWN_HEADING_RE.match(line)
        if heading_match:
            flush_current_section()
            current_lines = []
            level = len(heading_match.group(1))
            title = clean_heading_text(heading_match.group(2))
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current_lines.append(line)
            continue

        current_lines.append(line)

    flush_current_section()

    if segments:
        return segments

    fallback_metadata = dict(base_metadata)
    fallback_metadata["section_title"] = "Document"
    fallback_metadata["section_path"] = "Document"
    return [SectionSegment(text=combined_text.strip(), metadata=fallback_metadata)]


def segment_pdf_documents(docs: List[Document]) -> List[SectionSegment]:
    segments: List[SectionSegment] = []

    for doc in docs:
        page_number = normalize_page_number((doc.metadata or {}).get("page"))
        page_label = f"Page {page_number}" if page_number is not None else "Document"
        base_metadata = dict(doc.metadata or {})
        base_metadata["page"] = page_number
        segments.extend(
            segment_generic_text(
                text=doc.page_content,
                base_metadata=base_metadata,
                base_path_parts=[page_label],
            )
        )

    return segments


def segment_text_documents(docs: List[Document]) -> List[SectionSegment]:
    segments: List[SectionSegment] = []

    for doc in docs:
        base_metadata = dict(doc.metadata or {})
        segments.extend(
            segment_generic_text(
                text=doc.page_content,
                base_metadata=base_metadata,
                base_path_parts=[],
            )
        )

    return segments


def segment_generic_text(
    text: str,
    base_metadata: dict,
    base_path_parts: list[str],
) -> List[SectionSegment]:
    if not text.strip():
        return []

    lines = text.splitlines()
    current_lines: list[str] = []
    current_heading: Optional[str] = None
    segments: List[SectionSegment] = []

    def flush_current_section() -> None:
        section_text = "\n".join(current_lines).strip()
        if not section_text:
            return

        metadata = dict(base_metadata)
        section_title = current_heading or (
            base_path_parts[-1] if base_path_parts else "Document"
        )
        if current_heading and is_heading_only_block(section_text, current_heading):
            return

        path_parts = [*base_path_parts]
        if current_heading:
            path_parts.append(current_heading)
        section_path = " > ".join(part for part in path_parts if part) or "Document"
        metadata["section_title"] = section_title
        metadata["section_path"] = section_path
        segments.append(SectionSegment(text=section_text, metadata=metadata))

    for line in lines:
        if is_heading_candidate(line):
            flush_current_section()
            current_lines = []
            current_heading = clean_heading_text(line)
            current_lines.append(line)
            continue

        current_lines.append(line)

    flush_current_section()

    if segments:
        return segments

    fallback_metadata = dict(base_metadata)
    fallback_metadata["section_title"] = (
        base_path_parts[-1] if base_path_parts else "Document"
    )
    fallback_metadata["section_path"] = " > ".join(base_path_parts) or "Document"
    return [SectionSegment(text=text.strip(), metadata=fallback_metadata)]


def build_section_content(text: str, section_path: str | None) -> str:
    cleaned_text = text.strip()
    if not cleaned_text:
        return cleaned_text

    if section_path and section_path != "Document":
        return f"Section: {section_path}\n\n{cleaned_text}"

    return cleaned_text


def clean_heading_text(text: str) -> str:
    stripped = text.strip().lstrip("#").strip()
    return stripped.rstrip(":").strip()


def is_heading_only_block(text: str, section_title: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        return False

    return clean_heading_text(lines[0]) == clean_heading_text(section_title)


def normalize_page_number(page_value: object) -> int | None:
    if page_value is None:
        return None

    try:
        return int(page_value) + 1
    except (TypeError, ValueError):
        return None


def is_heading_candidate(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    if len(stripped) > 100:
        return False

    if stripped.startswith(("#", "-", "*")):
        return False

    if NUMBERED_HEADING_RE.match(stripped):
        return True

    words = stripped.split()
    if len(words) > 12:
        return False

    if stripped.endswith(":") and len(words) <= 10:
        return True

    alpha_words = [word for word in words if any(char.isalpha() for char in word)]
    if not alpha_words:
        return False

    uppercase_words = sum(word.isupper() for word in alpha_words)
    title_case_words = sum(
        word[:1].isupper() and word[1:].lower() == word[1:]
        for word in alpha_words
        if word
    )

    uppercase_ratio = uppercase_words / len(alpha_words)
    title_case_ratio = title_case_words / len(alpha_words)

    if uppercase_ratio >= 0.6 and len(alpha_words) <= 8:
        return True

    if (
        title_case_ratio >= 0.8
        and len(alpha_words) <= 10
        and not stripped.endswith(".")
    ):
        return True

    return False
