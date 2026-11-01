"""Step 1 of the pipeline: get plain text out of PDF, DOCX and TXT files."""
from dataclasses import dataclass
from io import BytesIO


class DocumentError(Exception):
    """A problem with the uploaded file. The message is safe to show to the user."""


@dataclass
class Page:
    number: int | None  # PDF page number; None for DOCX/TXT, which have no fixed pages
    text: str


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def has_valid_signature(ext: str, data: bytes) -> bool:
    """Check the file's first bytes, so a renamed .exe can't pass as a .pdf."""
    if ext == ".pdf":
        return data[:1024].lstrip().startswith(b"%PDF-")
    if ext == ".docx":
        return data[:2] == b"PK"  # DOCX is a ZIP archive
    if ext == ".txt":
        return b"\x00" not in data[:4096]
    return False


def load_document(ext: str, data: bytes) -> list[Page]:
    loader = {".pdf": _load_pdf, ".docx": _load_docx, ".txt": _load_txt}[ext]
    pages = loader(data)
    if not any(p.text.strip() for p in pages):
        raise DocumentError(
            "No readable text was found in this document. Scanned or image-only files are not supported."
        )
    return pages


def _load_pdf(data: bytes) -> list[Page]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError("This PDF is password-protected. Remove the password and upload it again.")
        return [Page(i, page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
    except DocumentError:
        raise
    except Exception as exc:  # pypdf raises many different error types for damaged files
        raise DocumentError("This PDF appears to be corrupted or unreadable.") from exc


def _load_docx(data: bytes) -> list[Page]:
    from docx import Document

    try:
        doc = Document(BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return [Page(None, "\n".join(parts))]
    except Exception as exc:
        raise DocumentError("This Word file appears to be corrupted or is not a valid .docx.") from exc


def _load_txt(data: bytes) -> list[Page]:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return [Page(None, data.decode(encoding))]
        except UnicodeError:
            continue
    raise DocumentError("This text file uses an encoding that could not be read.")
