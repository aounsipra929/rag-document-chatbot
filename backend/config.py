"""Application settings. Everything comes from environment variables (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = DATA_DIR / "indexes"
DATA_DIR.mkdir(exist_ok=True)
INDEX_DIR.mkdir(exist_ok=True)

# Values already set in the real environment win. backend/.env is read first, then ../.env
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class Settings:
    def __init__(self) -> None:
        self.app_env = _get("APP_ENV", "development").lower()

        # OpenAI
        self.openai_api_key = _get("OPENAI_API_KEY")
        self.openai_base_url = _get("OPENAI_BASE_URL")  # empty = OpenAI. OpenRouter: https://openrouter.ai/api/v1
        self.use_json_mode = _get("USE_JSON_MODE", "true").lower() == "true"  # set false for most free models
        self.chat_model = _get("OPENAI_CHAT_MODEL")
        self.embedding_model = _get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.temperature = _get("OPENAI_TEMPERATURE")

        # Retrieval
        self.relevance_threshold = float(_get("RELEVANCE_THRESHOLD", "0.35"))
        self.top_k = int(_get("TOP_K", "5"))
        self.chunk_size = int(_get("CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(_get("CHUNK_OVERLAP", "200"))

        # Uploads
        self.max_upload_mb = int(_get("MAX_UPLOAD_MB", "10"))
        self.max_docs_per_user = int(_get("MAX_DOCS_PER_USER", "20"))

        # Database
        self.database_url = _get("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}")

        # Auth / security
        self.jwt_secret = _get("JWT_SECRET")
        self.access_token_minutes = int(_get("ACCESS_TOKEN_MINUTES", "60"))
        self.cors_origins = [o.strip() for o in _get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
        self.allow_registration = _get("ALLOW_REGISTRATION", "true").lower() == "true"
        self.max_failed_logins = 5
        self.lockout_minutes = 15

        # First admin
        self.admin_email = _get("ADMIN_EMAIL").lower()
        self.admin_password = _get("ADMIN_PASSWORD")
        self.admin_name = _get("ADMIN_NAME", "Administrator")

    @property
    def is_dev(self) -> bool:
        return self.app_env != "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def validate(self) -> None:
        problems = []
        if len(self.jwt_secret) < 32:
            problems.append(
                "JWT_SECRET is missing or shorter than 32 characters. Generate one with:\n"
                '     python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if not 0 <= self.relevance_threshold <= 1:
            problems.append("RELEVANCE_THRESHOLD must be between 0 and 1.")
        if self.chunk_overlap >= self.chunk_size:
            problems.append("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        if problems:
            raise RuntimeError("Configuration problems:\n - " + "\n - ".join(problems))


settings = Settings()
