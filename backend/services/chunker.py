"""Step 2: clean the text and cut it into overlapping chunks that remember where they came from."""
import re

from services.document_loader import Page

MIN_CHUNK_CHARS = 20


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)  # collapse runs of spaces/tabs
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # at most one blank line
    return text.strip()


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Cut `text` into pieces of about `size` characters; each piece starts `overlap` characters
    before the previous one ended, so a sentence on a boundary appears whole in at least one chunk."""
    chunks: list[str] = []
    n, start = len(text), 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", "\n", ". ", " "):  # prefer to cut at a paragraph, line, sentence, then word
                idx = window.rfind(sep)
                if idx >= size * 0.6:
                    end = start + idx + len(sep)
                    break
        piece = text[start:end].strip()
        if len(piece) >= MIN_CHUNK_CHARS:
            chunks.append(piece)
        if end >= n:
            break
        start = end - overlap if end - overlap > start else end  # always move forward
    return chunks


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[dict]:
    """Return [{"chunk_index": 0, "page": 3, "text": "..."}]. Chunks never cross a page boundary,
    so the page number attached to a chunk is always correct."""
    result: list[dict] = []
    for page in pages:
        for piece in split_text(clean_text(page.text), size, overlap):
            result.append({"chunk_index": len(result), "page": page.number, "text": piece})
    return result
