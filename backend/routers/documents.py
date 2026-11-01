"""Upload, list and delete documents (only ever the caller's own)."""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import current_user, current_user_web
from models import Chunk, Document, User
from schemas import DocumentOut
from security import upload_limiter
from services.chunker import chunk_pages
from services.document_loader import ALLOWED_EXTENSIONS, DocumentError, has_valid_signature, load_document
from services.embeddings import AIServiceError, embed_texts
from services.vector_store import vector_store

router = APIRouter(prefix="/api", tags=["documents"])


def _safe_filename(name: str | None) -> str:
    name = Path((name or "document").replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]", "", name).strip()
    return name[:150] or "document"


def remove_document(db: Session, doc: Document) -> None:
    """Delete a document's database rows AND its vectors."""
    vector_store.remove(doc.user_id, [c.id for c in doc.chunks])
    db.delete(doc)
    db.commit()


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload(file: UploadFile = File(...), user: User = Depends(current_user_web), db: Session = Depends(get_db)):
    upload_limiter.hit(f"user:{user.id}")

    filename = _safe_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Unsupported file type. Please upload a PDF, DOCX or TXT file.")
    if db.query(Document).filter(Document.user_id == user.id).count() >= settings.max_docs_per_user:
        raise HTTPException(400, f"You can keep up to {settings.max_docs_per_user} documents. Remove one to add another.")

    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"This file is too large. The limit is {settings.max_upload_mb} MB.")
    if not data:
        raise HTTPException(400, "This file is empty.")
    if not has_valid_signature(ext, data):
        raise HTTPException(400, f"The contents of this file don't look like a real {ext[1:].upper()} file.")

    try:
        pages = load_document(ext, data)
        chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise DocumentError("No readable text was found in this document.")
        vectors = embed_texts([c["text"] for c in chunks])
    except DocumentError as exc:
        raise HTTPException(422, str(exc))
    except AIServiceError as exc:
        raise HTTPException(502, str(exc))

    doc = Document(
        user_id=user.id,
        filename=filename,
        file_type=ext[1:],
        size_bytes=len(data),
        page_count=len(pages) if ext == ".pdf" else None,
        chunk_count=len(chunks),
    )
    doc.chunks = [Chunk(chunk_index=c["chunk_index"], page=c["page"], text=c["text"]) for c in chunks]
    db.add(doc)
    db.flush()  # assigns the chunk ids that we use as FAISS ids
    ids = [c.id for c in doc.chunks]
    try:
        vector_store.add(user.id, ids, vectors)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            vector_store.remove(user.id, ids)
        except Exception:
            pass
        if isinstance(exc, AIServiceError):
            raise HTTPException(409, str(exc))
        raise HTTPException(500, "The document could not be saved. Please try again.")
    return doc


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Document).filter(Document.user_id == user.id).order_by(Document.created_at.desc()).all()


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, user: User = Depends(current_user_web), db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:  # someone else's document looks exactly like a missing one
        raise HTTPException(404, "Document not found.")
    remove_document(db, doc)


@router.post("/clear")
def clear(user: User = Depends(current_user_web), db: Session = Depends(get_db)):
    """Remove all of the caller's documents and vectors. (Chat history lives in the browser.)"""
    docs = db.query(Document).filter(Document.user_id == user.id).all()
    for doc in docs:
        db.delete(doc)
    db.commit()
    vector_store.drop(user.id)
    return {"deleted": len(docs)}
