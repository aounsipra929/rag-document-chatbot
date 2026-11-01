"""Tests for the pure-Python parts of the pipeline (no OpenAI key or network needed)."""
from io import BytesIO

import pytest

from services.chunker import chunk_pages, clean_text, split_text
from services.document_loader import DocumentError, Page, has_valid_signature, load_document


def test_clean_text_collapses_whitespace():
    assert clean_text("a   b\t\tc\n\n\n\nd \x00") == "a b c\n\nd"


def test_split_text_overlaps_and_respects_size():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = split_text(text, size=200, overlap=40)
    assert len(chunks) > 5
    assert all(len(c) <= 200 for c in chunks)
    # overlap: the start of each chunk repeats something from the end of the previous one
    assert chunks[1].split()[0] in chunks[0]


def test_split_text_always_terminates():
    assert split_text("x" * 5000, size=100, overlap=99)  # no infinite loop on unbroken text


def test_chunks_keep_page_numbers_and_running_index():
    pages = [Page(1, "First page text. " * 10), Page(2, "Second page text. " * 10)]
    chunks = chunk_pages(pages, size=100, overlap=20)
    assert {c["page"] for c in chunks} == {1, 2}
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_txt_and_empty_documents():
    assert load_document(".txt", b"Hello there, this is a document.")[0].text.startswith("Hello")
    with pytest.raises(DocumentError):
        load_document(".txt", b"   \n  ")


def test_corrupted_pdf_is_a_friendly_error():
    with pytest.raises(DocumentError, match="corrupted"):
        load_document(".pdf", b"%PDF-1.4 this is not really a pdf")


def test_docx_round_trip():
    from docx import Document

    doc = Document()
    doc.add_paragraph("Annual leave is 25 days per year.")
    buf = BytesIO()
    doc.save(buf)
    pages = load_document(".docx", buf.getvalue())
    assert "25 days" in pages[0].text


def test_signature_check_rejects_renamed_files():
    assert not has_valid_signature(".pdf", b"MZ\x90\x00 executable")
    assert has_valid_signature(".pdf", b"%PDF-1.7 ...")
    assert not has_valid_signature(".docx", b"not a zip")
