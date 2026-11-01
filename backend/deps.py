"""FastAPI dependencies that decide WHO is calling and WHAT they may do."""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import ApiToken, User, utcnow
from security import API_TOKEN_PREFIX, decode_access_token, hash_api_token

bearer = HTTPBearer(auto_error=False)


def _authenticate(request: Request, creds: HTTPAuthorizationCredentials | None, db: Session, allow_api_token: bool) -> User:
    unauthorized = HTTPException(401, "Please sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    token = creds.credentials
    user: User | None = None

    if token.startswith(API_TOKEN_PREFIX):
        if not allow_api_token:
            raise HTTPException(403, "API tokens can only be used for /api/chat and GET /api/documents.")
        row = db.query(ApiToken).filter(ApiToken.token_hash == hash_api_token(token)).first()
        if row:
            row.last_used_at = utcnow()
            db.commit()
            user = row.user
        request.state.channel = "api"
    else:
        user_id = decode_access_token(token)
        user = db.get(User, user_id) if user_id else None
        request.state.channel = "web"

    if user is None or not user.is_active:
        raise unauthorized
    return user


def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    """Login token OR API token. Used only by the chatbot endpoints."""
    return _authenticate(request, creds, db, allow_api_token=True)


def current_user_web(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    """Login token only (API tokens are rejected). Used by everything that changes data."""
    return _authenticate(request, creds, db, allow_api_token=False)


def require_admin(user: User = Depends(current_user_web)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin access required.")
    return user
