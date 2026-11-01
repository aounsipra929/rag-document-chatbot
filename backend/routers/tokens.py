"""API tokens: long-lived keys a user can create to call the chatbot from their own scripts."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from deps import current_user_web
from models import ApiToken, User
from schemas import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from security import generate_api_token

router = APIRouter(prefix="/api/tokens", tags=["api tokens"])
MAX_TOKENS_PER_USER = 5


@router.get("", response_model=list[ApiTokenOut])
def list_tokens(user: User = Depends(current_user_web), db: Session = Depends(get_db)):
    return db.query(ApiToken).filter(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc()).all()


@router.post("", response_model=ApiTokenCreated, status_code=201)
def create_token(body: ApiTokenCreate, user: User = Depends(current_user_web), db: Session = Depends(get_db)):
    if db.query(ApiToken).filter(ApiToken.user_id == user.id).count() >= MAX_TOKENS_PER_USER:
        raise HTTPException(400, f"You can have up to {MAX_TOKENS_PER_USER} API tokens. Revoke one first.")
    raw, token_hash = generate_api_token()
    row = ApiToken(user_id=user.id, name=body.name, token_hash=token_hash, prefix=raw[:8])
    db.add(row)
    db.commit()
    return ApiTokenCreated(**ApiTokenOut.model_validate(row).model_dump(), token=raw)


@router.delete("/{token_id}", status_code=204)
def revoke_token(token_id: int, user: User = Depends(current_user_web), db: Session = Depends(get_db)):
    row = db.get(ApiToken, token_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Token not found.")
    db.delete(row)
    db.commit()
