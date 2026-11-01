"""Request/response shapes (Pydantic). Validation messages are written for end users."""
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 255 or not EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address.")
    return v


Email = Annotated[str, AfterValidator(_check_email)]


# ---------- auth ----------
class RegisterRequest(BaseModel):
    email: Email
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter your name.")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain at least one letter and one number.")
        return v


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------- documents ----------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    file_type: str
    size_bytes: int
    page_count: int | None = None
    chunk_count: int
    created_at: datetime


# ---------- chat ----------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str
    conversation_history: list[ChatMessage] = Field(default_factory=list, max_length=20)

    @field_validator("question")
    @classmethod
    def _question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Please type a question.")
        if len(v) > 2000:
            raise ValueError("Your question is too long (2000 characters maximum).")
        return v


class Source(BaseModel):
    filename: str
    page: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)

    @field_validator("text")
    @classmethod
    def _text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Please provide some text to speak.")
        return v


# ---------- API tokens ----------
class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Give the token a name.")
        return v


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiTokenCreated(ApiTokenOut):
    token: str  # shown once, never stored


# ---------- admin ----------
class AdminUserUpdate(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class AdminUserOut(UserOut):
    document_count: int


class AdminDocumentOut(DocumentOut):
    owner_email: str


class ChatLogOut(BaseModel):
    id: int
    user_email: str
    question: str
    answered: bool
    top_score: float | None
    channel: str
    created_at: datetime


class StatsOut(BaseModel):
    total_users: int
    active_users: int
    admins: int
    total_documents: int
    total_chunks: int
    questions_total: int
    questions_answered: int
    questions_not_found: int
    questions_last_7_days: int
