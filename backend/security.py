"""Server-side security helpers: password hashing, JWTs, API tokens, rate limiting, HTTP headers."""
import base64
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

# ---------------------------------------------------------------- passwords
def _prepare(password: str) -> bytes:
    # bcrypt only reads the first 72 bytes. Hashing first lets long passwords work safely.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except ValueError:
        return False


# Verified against when the email is unknown, so "no such user" and "wrong password" take equally long.
DUMMY_HASH = hash_password("not-a-real-password")


# ---------------------------------------------------------------- JWT access tokens
def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,  # informational only: the server always re-reads the role from the database
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    """Return the user id, or None if the token is invalid, expired or the wrong kind."""
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        if data.get("type") != "access":
            return None
        return int(data["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


# ---------------------------------------------------------------- API tokens (for scripts / integrations)
API_TOKEN_PREFIX = "dqa_"


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). The raw token is shown to the user once and never stored."""
    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_token(raw)


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """Sliding-window limiter kept in memory (fine for one server process; use Redis for several)."""

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name, self.limit, self.window = name, limit, window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                retry = int(self.window - (now - q[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please wait a moment and try again.",
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)

    def __call__(self, request: Request) -> None:  # usable as Depends(limiter): limits per client IP
        self.hit(request.client.host if request.client else "unknown")


login_limiter = RateLimiter("login", 10, 60)
register_limiter = RateLimiter("register", 5, 3600)
chat_limiter = RateLimiter("chat", 30, 60)
upload_limiter = RateLimiter("upload", 10, 60)


# ---------------------------------------------------------------- HTTP security headers + body-size guard
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_upload_bytes + 1_000_000:
            return JSONResponse(
                status_code=413,
                content={"detail": f"That request is too large. Files can be up to {settings.max_upload_mb} MB."},
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.url.path.startswith(self.DOC_PATHS):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if not settings.is_dev:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
