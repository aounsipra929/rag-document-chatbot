"""Document Q&A Chatbot - FastAPI entry point.  Run:  uvicorn main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import Base, SessionLocal, engine
from models import User
from routers import admin, auth, chat, documents, tokens
from security import SecurityHeadersMiddleware, hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("docqa")


def seed_admin() -> None:
    """Create the first admin from ADMIN_EMAIL / ADMIN_PASSWORD if that account doesn't exist yet."""
    if not (settings.admin_email and settings.admin_password):
        log.warning("ADMIN_EMAIL / ADMIN_PASSWORD not set - no admin account was created.")
        return
    if len(settings.admin_password) < 8:
        log.warning("ADMIN_PASSWORD is shorter than 8 characters - no admin account was created.")
        return
    with SessionLocal() as db:
        if db.query(User).filter(User.email == settings.admin_email).first():
            return
        db.add(
            User(
                email=settings.admin_email,
                name=settings.admin_name,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
        )
        db.commit()
        log.info("Created admin account %s", settings.admin_email)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate()
    Base.metadata.create_all(engine)  # for real deployments, manage schema changes with Alembic
    seed_admin()
    if not settings.openai_api_key:
        log.warning("OPENAI_API_KEY is not set - uploads and chat will fail until you add it to .env")
    if not settings.chat_model:
        log.warning("OPENAI_CHAT_MODEL is not set - chat will fail until you add it to .env")
    yield


app = FastAPI(
    title="Document Q&A Chatbot",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_dev else None,  # interactive API docs only in development
    redoc_url=None,
    openapi_url="/openapi.json" if settings.is_dev else None,
)

# The last middleware added is the outermost, so CORS goes last and also covers error responses.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # explicit list, never "*"
    allow_credentials=False,  # we use Authorization headers, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    err = exc.errors()[0]
    msg = str(err.get("msg", "Invalid request."))
    if msg.startswith("Value error, "):
        msg = msg.removeprefix("Value error, ")
    else:
        field = str(err["loc"][-1]) if err.get("loc") else "request"
        msg = f"Invalid {field}: {msg}"
    return JSONResponse(status_code=422, content={"detail": msg})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. Please try again."})


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


for module in (auth, documents, chat, tokens, admin):
    app.include_router(module.router)
