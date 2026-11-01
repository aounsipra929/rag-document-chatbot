"""End-to-end API test with OpenAI replaced by fakes, so it needs no API key or network.

Run from the backend folder:  pip install -r requirements-dev.txt && pytest -q
"""
import json
import os
import re
import tempfile
import zlib
from pathlib import Path

import numpy as np
import pytest

# Configure BEFORE the app is imported (config.py reads the environment at import time).
_tmp = tempfile.mkdtemp()
os.environ.update(
    {
        "APP_ENV": "development",
        "JWT_SECRET": "t" * 48,
        "DATABASE_URL": f"sqlite:///{Path(_tmp, 'test.db').as_posix()}",
        "ADMIN_EMAIL": "admin@test.com",
        "ADMIN_PASSWORD": "Admin12345",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_CHAT_MODEL": "fake-model",
        "RELEVANCE_THRESHOLD": "0.3",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

import routers.documents as documents_router  # noqa: E402
import services.qa_service as qa  # noqa: E402
import services.vector_store as vs  # noqa: E402
from main import app  # noqa: E402

vs.INDEX_DIR = Path(_tmp, "indexes")  # keep test vectors out of the real data folder
vs.INDEX_DIR.mkdir()

chat_calls: list[bool] = []


def fake_embed(texts):
    """Bag-of-words hashing: texts sharing words get similar vectors. Enough to test retrieval logic."""
    out = np.zeros((len(texts), 256), dtype="float32")
    for i, text in enumerate(texts):
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            out[i, zlib.crc32(word.encode()) % 256] += 1
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return out / norms


def fake_chat(messages, json_mode=False):
    chat_calls.append(json_mode)
    if json_mode:
        return json.dumps({"answer": "The training program lasts 12 weeks.", "used_sources": [1]})
    return "How long is the training program?"  # the follow-up rewriter


@pytest.fixture(scope="module")
def client():
    documents_router.embed_texts = fake_embed
    qa.embed_texts = fake_embed
    qa._chat = fake_chat
    with TestClient(app) as c:
        yield c


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, email):
    r = client.post("/api/auth/register", json={"email": email, "name": email.split("@")[0], "password": "Passw0rd123"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def test_full_workflow(client):
    # --- admin and user roles
    r = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "Admin12345"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    admin = r.json()["access_token"]
    assert client.get("/api/admin/stats", headers=_auth(admin)).status_code == 200

    alice, bob = _register(client, "alice@test.com"), _register(client, "bob@test.com")
    assert client.get("/api/admin/stats", headers=_auth(alice)).status_code == 403
    assert client.get("/api/admin/users").status_code == 401

    # --- bad logins and bad uploads
    assert client.post("/api/auth/login", json={"email": "alice@test.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/upload", headers=_auth(alice), files={"file": ("a.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert client.post("/api/upload", headers=_auth(alice), files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}).status_code == 400
    assert client.post("/api/upload", headers=_auth(alice), files={"file": ("e.txt", b"", "text/plain")}).status_code == 400

    # --- no documents yet
    assert client.post("/api/chat", headers=_auth(alice), json={"question": "Anything?"}).status_code == 400

    # --- upload
    text = b"The training program lasts 12 weeks. Employees receive a mentor during the program."
    r = client.post("/api/upload", headers=_auth(alice), files={"file": ("handbook.txt", text, "text/plain")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["chunk_count"] >= 1

    # --- answer that IS in the document
    r = client.post("/api/chat", headers=_auth(alice), json={"question": "How long is the training program?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "The training program lasts 12 weeks."
    assert r.json()["sources"] == [{"filename": "handbook.txt", "page": None}]
    calls_after_first = len(chat_calls)
    assert calls_after_first == 1

    # --- answer that is NOT in the document: the model must not even be called
    r = client.post("/api/chat", headers=_auth(alice), json={"question": "What is the capital of France?"})
    assert r.json() == {"answer": qa.NOT_FOUND, "sources": []}
    assert len(chat_calls) == calls_after_first

    # --- follow-up question uses the rewriter, then the normal path
    history = [{"role": "user", "content": "How long is the training program?"}, {"role": "assistant", "content": "12 weeks."}]
    r = client.post("/api/chat", headers=_auth(alice), json={"question": "Is that paid?", "conversation_history": history})
    assert r.status_code == 200 and chat_calls[-2:] == [False, True]

    # --- empty question
    r = client.post("/api/chat", headers=_auth(alice), json={"question": "   "})
    assert r.status_code == 422 and r.json()["detail"] == "Please type a question."

    # --- isolation between users
    assert client.get("/api/documents", headers=_auth(bob)).json() == []
    assert client.post("/api/chat", headers=_auth(bob), json={"question": "training program"}).status_code == 400
    assert client.delete(f"/api/documents/{doc['id']}", headers=_auth(bob)).status_code == 404

    # --- API tokens: chat + list documents only
    r = client.post("/api/tokens", headers=_auth(alice), json={"name": "script"})
    assert r.status_code == 201
    api_token = r.json()["token"]
    assert api_token.startswith("dqa_")
    assert client.post("/api/chat", headers=_auth(api_token), json={"question": "How long is the training program?"}).status_code == 200
    assert len(client.get("/api/documents", headers=_auth(api_token)).json()) == 1
    assert client.post("/api/upload", headers=_auth(api_token), files={"file": ("x.txt", text, "text/plain")}).status_code == 403
    assert client.get("/api/tokens", headers=_auth(api_token)).status_code == 403

    # --- admin sees activity, cannot demote self
    assert client.get("/api/admin/stats", headers=_auth(admin)).json()["questions_total"] >= 3
    assert len(client.get("/api/admin/documents", headers=_auth(admin)).json()) == 1
    me = client.get("/api/auth/me", headers=_auth(admin)).json()
    assert client.patch(f"/api/admin/users/{me['id']}", headers=_auth(admin), json={"role": "user"}).status_code == 400

    # --- delete removes the document and its vectors
    assert client.delete(f"/api/documents/{doc['id']}", headers=_auth(alice)).status_code == 204
    assert client.get("/api/documents", headers=_auth(alice)).json() == []
    assert client.post("/api/chat", headers=_auth(alice), json={"question": "How long is the training program?"}).status_code == 400
