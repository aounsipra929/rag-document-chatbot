"""Admin-only endpoints. Every route in this router requires role == 'admin'.

Admins can manage accounts and see document METADATA, but there is deliberately no endpoint that
returns another user's document text.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from deps import require_admin
from models import ChatLog, Chunk, Document, User, utcnow
from routers.documents import remove_document
from schemas import AdminDocumentOut, AdminUserOut, AdminUserUpdate, ChatLogOut, DocumentOut, StatsOut, UserOut
from services.vector_store import vector_store

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    def count(model, *filters):
        return db.query(func.count(model.id)).filter(*filters).scalar() or 0

    answered = count(ChatLog, ChatLog.answered.is_(True))
    total = count(ChatLog)
    return StatsOut(
        total_users=count(User),
        active_users=count(User, User.is_active.is_(True)),
        admins=count(User, User.role == "admin"),
        total_documents=count(Document),
        total_chunks=count(Chunk),
        questions_total=total,
        questions_answered=answered,
        questions_not_found=total - answered,
        questions_last_7_days=count(ChatLog, ChatLog.created_at >= utcnow() - timedelta(days=7)),
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    counts = dict(db.query(Document.user_id, func.count(Document.id)).group_by(Document.user_id).all())
    users = db.query(User).order_by(User.created_at).all()
    return [
        AdminUserOut(**UserOut.model_validate(u).model_dump(), document_count=counts.get(u.id, 0)) for u in users
    ]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: AdminUserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found.")
    if target.id == admin.id:
        raise HTTPException(400, "You can't change your own role or deactivate yourself.")
    if body.role is not None:
        target.role = body.role
    if body.is_active is not None:
        target.is_active = body.is_active
    db.commit()
    return target


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found.")
    if target.id == admin.id:
        raise HTTPException(400, "You can't delete your own account.")
    db.delete(target)  # cascades to documents, chunks, tokens and logs
    db.commit()
    vector_store.drop(user_id)


@router.get("/documents", response_model=list[AdminDocumentOut])
def all_documents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(Document, User.email).join(User, Document.user_id == User.id).order_by(Document.created_at.desc()).all()
    return [AdminDocumentOut(**DocumentOut.model_validate(doc).model_dump(), owner_email=email) for doc, email in rows]


@router.delete("/documents/{document_id}", status_code=204)
def delete_any_document(document_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    remove_document(db, doc)


@router.get("/chat-logs", response_model=list[ChatLogOut])
def chat_logs(limit: int = 50, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    limit = max(1, min(limit, 200))
    rows = (
        db.query(ChatLog, User.email)
        .join(User, ChatLog.user_id == User.id)
        .order_by(ChatLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        ChatLogOut(
            id=log.id, user_email=email, question=log.question, answered=log.answered,
            top_score=log.top_score, channel=log.channel, created_at=log.created_at,
        )
        for log, email in rows
    ]
