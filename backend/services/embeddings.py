"""Step 3: turn text into vectors with the OpenAI embeddings API (server-side only)."""
import io
import logging

import numpy as np
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from config import settings

log = logging.getLogger(__name__)


class AIServiceError(Exception):
    """OpenAI (or the vector index) failed. The message is safe to show to the user."""


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if not settings.openai_api_key:
        raise AIServiceError("The server has no OpenAI API key configured. Ask the administrator to set OPENAI_API_KEY.")
    if _client is None:
        _client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=60,
            max_retries=1,
        )
    return _client


def explain_openai_error(exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        return "The OpenAI API key was rejected. Ask the administrator to check OPENAI_API_KEY."
    if isinstance(exc, RateLimitError):
        return "The AI provider's rate limit or daily quota was reached. Wait a little and try again."
    if isinstance(exc, APIConnectionError):
        return "Could not reach the AI provider. Check the server's internet connection and try again."
    if isinstance(exc, NotFoundError):
        return "The configured AI model was not found or is unavailable. Ask the administrator to check the model name."
    if isinstance(exc, BadRequestError):
        return "The AI provider could not process this request."
    return "The AI service returned an error. Please try again."


def transcribe_audio(audio_bytes: bytes, filename: str = "voice.webm") -> str:
    """Use the server-side OpenAI API key to convert microphone audio to text."""
    client = get_client()
    try:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename or "voice.webm", io.BytesIO(audio_bytes), "audio/webm"),
        )
        text = getattr(response, "text", "")
        cleaned = text.strip()
        if not cleaned:
            raise AIServiceError("No speech was detected.")
        return cleaned
    except OpenAIError as exc:
        log.warning("Audio transcription call failed: %r", exc)
        raise AIServiceError(explain_openai_error(exc)) from exc


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return an (n, dim) float32 array of L2-normalised vectors.
    Normalising means the FAISS inner product equals cosine similarity."""
    client = get_client()
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), 64):
            resp = client.embeddings.create(model=settings.embedding_model, input=texts[i : i + 64], encoding_format="float"
            )
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
    except OpenAIError as exc:
        log.warning("Embedding call failed: %r", exc)  # the real reason, for the terminal
        raise AIServiceError(explain_openai_error(exc)) from exc

    arr = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def text_to_speech(text: str, voice: str = "alloy") -> bytes:
    """Use the OpenAI audio API to convert text into speech (MP3 by default)."""
    client = get_client()
    try:
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
        )
        audio = response.read()
        if not audio:
            raise AIServiceError("The speech API returned no audio.")
        return audio
    except OpenAIError as exc:
        log.warning("Text-to-speech call failed: %r", exc)
        raise AIServiceError(explain_openai_error(exc)) from exc
