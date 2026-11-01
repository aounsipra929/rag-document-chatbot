"""The chatbot endpoint. Accepts a login token OR an API token."""
import io
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from deps import current_user
from models import User
from schemas import ChatRequest, ChatResponse, SpeechRequest
from security import chat_limiter
from services.embeddings import AIServiceError, text_to_speech, transcribe_audio
from services.qa_service import NoDocumentsError, answer_question

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    chat_limiter.hit(f"user:{user.id}")
    try:
        answer, sources = answer_question(
            db, user, body.question, body.conversation_history, getattr(request.state, "channel", "web")
        )
    except NoDocumentsError:
        raise HTTPException(400, "Upload a document first, then ask your question.")
    except AIServiceError as exc:
        raise HTTPException(502, str(exc))
    return ChatResponse(answer=answer, sources=sources)


@router.post("/chat/speech")
def speech_route(body: SpeechRequest, user: User = Depends(current_user)):
    try:
        audio = text_to_speech(body.text)
    except AIServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return StreamingResponse(io.BytesIO(audio), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.post("/chat/transcribe")
def transcribe_audio_route(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
):
    if not file.filename:
        raise HTTPException(400, "No audio file was sent.")
    try:
        data = file.file.read()
        if not data:
            raise HTTPException(400, "The audio file is empty.")
        text = transcribe_audio(data, file.filename)
    except AIServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"text": text}
