"""Sign up, sign in, and 'who am I'."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import current_user_web
from models import User, utcnow
from schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    login_limiter,
    register_limiter,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=201, dependencies=[Depends(register_limiter)])
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(403, "Sign-ups are closed. Ask an administrator to create an account for you.")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "An account with this email already exists.")
    # Everyone who registers here is a normal user. Admins are created via ADMIN_EMAIL or by another admin.
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password), role="user")
    user.last_login_at = utcnow()
    db.add(user)
    db.commit()
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(login_limiter)])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    now = utcnow()

    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(429, f"Too many failed attempts. Try again in {settings.lockout_minutes} minutes.")

    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not password_ok:
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_attempts = 0
            db.commit()
        raise HTTPException(401, "Incorrect email or password.")  # same message for both cases

    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated. Contact an administrator.")

    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
    db.commit()
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user_web)):
    return user
