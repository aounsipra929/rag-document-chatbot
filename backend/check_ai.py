"""Checks that your AI key and model names work, BEFORE you start the website.

Run from the backend folder (with the virtual environment active):   python check_ai.py
"""
from config import settings
from services.embeddings import AIServiceError, embed_texts
from services.qa_service import _chat

print("Provider address :", settings.openai_base_url or "OpenAI (default)")
print("Chat model       :", settings.chat_model or "(NOT SET)")
print("Embedding model  :", settings.embedding_model)
print("API key          :", "set" if settings.openai_api_key else "(NOT SET)")
print()

try:
    vec = embed_texts(["hello world"])
    print(f"[OK]   Embeddings work (vector size {vec.shape[1]}).")
except AIServiceError as exc:
    print("[FAIL] Embeddings:", exc)

try:
    reply = _chat([{"role": "user", "content": "Reply with the single word: ready"}])
    print("[OK]   Chat works. The model said:", reply[:80] or "(empty reply)")
except AIServiceError as exc:
    print("[FAIL] Chat:", exc)

print("\nIf something failed, look for a line starting with 'WARNING' above: it shows the exact reason.")
