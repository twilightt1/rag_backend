"""Text extraction and chunking utilities."""
import io
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter

log = logging.getLogger(__name__)


def extract_text(file_bytes: bytes, mime_type: str | None) -> str:
    mime = (mime_type or "").lower()

    if "pdf" in mime:
        return _extract_pdf(file_bytes)
    elif "wordprocessingml" in mime or "docx" in mime:
        return _extract_docx(file_bytes)
    else:
        # Plain text — try utf-8 then latin-1
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="replace")


def _extract_pdf(data: bytes) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text.strip())
    return "\n\n".join(text_parts)


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [c for c in splitter.split_text(text) if c.strip()]
