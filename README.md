# Document Q&A Chatbot

Upload PDF, DOCX or TXT files, then ask questions. The chatbot answers **only** from your documents, shows the file and page each answer came from, and says *"I couldn't find the answer to that in the uploaded document."* when the answer isn't there.

There are two roles:

| Role | Can do |
|------|--------|
| **user** | Upload and delete their own documents, chat with them, create API tokens |
| **admin** | Everything a user can, plus: see stats, manage users (role, activate/deactivate, delete), see every document's metadata (not its text), delete any document, review question activity |

## 1. Architecture

```
React (Vite)  ──HTTPS + Bearer token──▶  FastAPI  ──▶  SQLite / PostgreSQL   users, documents, chunks (text), tokens, logs
   browser                                  │     └──▶  FAISS (one index per user)   vectors only
                                            └────────▶  OpenAI API   embeddings + chat (key stays on the server)
```

**Database choice.** Relational data (users, roles, documents, chunk text, tokens, logs) lives in SQL through SQLAlchemy. It uses SQLite by default (zero setup) and switches to PostgreSQL by changing `DATABASE_URL`. Vectors live in FAISS, one index file per user in `backend/data/indexes/`. A chunk's database `id` is also its FAISS id, which is how a search hit becomes text, filename and page again.

## 2. Project structure

```
document-qa-chatbot/
├── .env.example            copy to .env and fill in
├── SECURITY.md             what protects the app, client and server
├── backend/
│   ├── main.py             app, CORS, error handlers, admin seeding
│   ├── config.py           all settings from .env
│   ├── database.py         SQLAlchemy engine/session
│   ├── models.py           tables
│   ├── schemas.py          request/response validation
│   ├── security.py         password hashing, JWT, API tokens, rate limits, security headers
│   ├── deps.py             "who is calling / are they admin"
│   ├── routers/            auth.py  documents.py  chat.py  tokens.py  admin.py
│   ├── services/           document_loader.py  chunker.py  embeddings.py  vector_store.py  qa_service.py
│   ├── tests/              test_pipeline.py  test_api_flow.py
│   └── data/               database + FAISS indexes (created at runtime, git-ignored)
└── frontend/
    ├── vite.config.js      dev proxy + production Content-Security-Policy
    ├── public/_headers     security headers for static hosts
    └── src/
        ├── App.jsx  main.jsx  api.js  security.js  format.js  styles.css
        └── components/     AuthPage  FileUpload  DocumentList  Chat  Message  Sources  ApiTokens  AdminPanel
```

## 3. Setup

Requires Python 3.10+, Node 18+, and an OpenAI API key.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Create `.env` and add your keys

```bash
cd ..                              # project root
cp .env.example .env               # Windows: copy .env.example .env
```

Open `.env` and set:

1. `OPENAI_API_KEY=` your key from platform.openai.com
2. `OPENAI_CHAT_MODEL=` the chat model you want to use (see section 8)
3. `JWT_SECRET=` a long random string. Generate one with:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
4. `ADMIN_EMAIL=` and `ADMIN_PASSWORD=` for the first admin account (8+ characters with a letter and a number)

`.env` is git-ignored. The OpenAI key is read only by the backend and never sent to the browser.

### Start FastAPI

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The first start creates the database and the admin account. Interactive API docs are at http://localhost:8000/docs (development only).

### Start React (second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Sign in with the admin account, or create a normal user with **Create an account**.

## 3a. Using a free OpenRouter key instead of OpenAI

1. Copy `.env.openrouter.example` to `.env` (instead of `.env.example`).
2. Replace the four `CHANGE-ME` values (OpenRouter key, JWT secret, admin email, admin password).
3. From `backend/`, run `python check_ai.py`. It tells you if the key and models work.
4. Start the backend and frontend as usual.

Notes: free accounts get about 50 requests per day and 20 per minute, and each question uses 2 to 3 requests. Free models may keep or train on what you send, so do not upload private documents. Free models change often: if a model stops working, pick another from openrouter.ai/models (search "free") and change `OPENAI_CHAT_MODEL`. `OPENAI_BASE_URL` makes the app talk to any OpenAI-compatible provider.

## 4. Test the whole workflow

1. Start the backend and the frontend (above).
2. Sign in, then drop a PDF into the upload area. You should see progress, then "Added. N text chunks extracted."
3. Ask a question whose answer is in the PDF. You get an answer with **Sources** (file and page).
4. Ask something that is not in the PDF, such as "What is the capital of France?"
5. You should get exactly: *I couldn't find the answer to that in the uploaded document.* with no sources.
6. Try a follow-up like "Is that also true for part-time staff?". The word "that" is resolved from your chat, but the facts still come from the document.
7. Sign in as a normal user in another browser: you cannot see the first user's documents, and the **Admin** tab is missing.

Automated tests (use fake OpenAI responses, no key or network needed):

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

## 5. How the RAG pipeline works

```
upload → extract text → clean + chunk (with overlap) → embed → store in FAISS (+ text in SQL)
question → (rewrite follow-up) → embed → FAISS search → threshold → build context → OpenAI → verify → answer + sources
```

* **Chunking:** about 1000 characters with 200 overlap, cut at paragraph/sentence boundaries. Chunks never cross a PDF page, so page numbers are exact. Change with `CHUNK_SIZE` / `CHUNK_OVERLAP`.
* **Vectors:** normalised, stored in a FAISS inner-product index, so the score is **cosine similarity** (1.0 = same meaning, near 0 = unrelated).
* **Only the top `TOP_K` chunks** (default 5) go to the model. The whole document is never sent.

## 6. How document-only answering is enforced

1. **Relevance threshold.** Chunks scoring below `RELEVANCE_THRESHOLD` are dropped. If none remain, the model is **not called** and the fixed "couldn't find" message is returned.
2. **Server-built context.** The frontend sends only the question and chat history. The backend builds the context from its own database; the browser cannot supply context.
3. **Strict system prompt** (in `services/qa_service.py`): use only the DOCUMENT CONTEXT, never general knowledge, reply with the exact not-found sentence otherwise, and treat document text as data, not instructions (prompt-injection defence).
4. **Answer verification.** The model must name the `[Source N]` blocks it used. An answer that cites no valid source is replaced with the not-found message.
5. **Sources come from the database, not the model**, so page numbers and filenames cannot be invented.
6. **History cannot become a source of truth.** Chat history is used only to rewrite a follow-up into a standalone search query. The answering step never sees it.

### Choosing the threshold

The spec example is `0.70`, but with `text-embedding-3-small` a chunk that genuinely answers a question usually scores only about **0.30 to 0.60** cosine similarity, so 0.70 would reject most valid questions. The default here is **0.35**. Tune it by checking the "Best match" column in Admin → Activity: raise it if off-topic questions get through, lower it if valid questions come back as "not found". Different embedding models have different score ranges.

## 7. API and tokens

Two kinds of bearer token, both sent as `Authorization: Bearer <token>`:

* **Login token (JWT):** returned by `POST /api/auth/login`, expires after `ACCESS_TOKEN_MINUTES` (default 60). Works everywhere the role allows.
* **API token (`dqa_...`):** created in the **API access** tab. Only for `POST /api/chat` and `GET /api/documents`. Stored hashed; shown once.

| Endpoint | Who |
|----------|-----|
| `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | public / signed in |
| `POST /api/upload`, `DELETE /api/documents/{id}`, `POST /api/clear` | user (login token) |
| `GET /api/documents`, `POST /api/chat` | user (login token or API token) |
| `GET/POST /api/tokens`, `DELETE /api/tokens/{id}` | user (login token) |
| `GET /api/admin/stats`, `/users`, `/documents`, `/chat-logs`, `PATCH/DELETE /api/admin/users/{id}`, `DELETE /api/admin/documents/{id}` | admin only |

`POST /api/chat` request and response:

```json
{ "question": "What is the annual leave policy?", "conversation_history": [] }
{ "answer": "…", "sources": [ { "filename": "handbook.pdf", "page": 4 } ] }
```

**Isolation.** Identity comes from the token, so the old `session_id` idea is replaced by real per-user isolation: separate FAISS index per user and every query filtered by owner. `POST /api/clear` removes all of the caller's documents and vectors; the chat itself lives in the browser (**Clear chat** button).

## 8. Change the OpenAI model

Edit `.env` and restart the backend:

```
OPENAI_CHAT_MODEL=<any chat model your account can use>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

If you change the **embedding** model, existing vectors no longer match. Users will see a message asking them to remove and re-upload their documents.

## 9. Common errors

| Message or symptom | Fix |
|--------------------|-----|
| `Configuration problems: JWT_SECRET is missing` on startup | Set `JWT_SECRET` in `.env` (command in section 3) |
| "The server has no OpenAI API key configured" | Set `OPENAI_API_KEY` in `.env`, restart uvicorn |
| "The server has no chat model configured" | Set `OPENAI_CHAT_MODEL` in `.env` |
| "The configured OpenAI model was not found" | Model name is wrong or not available to your account |
| "OpenAI rate limit or quota exceeded" | Check billing/usage on your OpenAI account |
| "Can't reach the server" in the browser | Backend not running on port 8000, or `VITE_API_URL` is wrong |
| CORS error in the browser console | Add your frontend URL to `CORS_ORIGINS` (dev uses the Vite proxy, so it shouldn't occur) |
| "No readable text was found" | The PDF is scanned images. OCR is not included |
| Everything answers "couldn't find" | Threshold too high for your embedding model. Lower `RELEVANCE_THRESHOLD` |
| Signed out unexpectedly | Token expired or 30 minutes idle. Sign in again |
| `faiss` fails to install | Use Python 3.10 to 3.12 and `pip install --upgrade pip` first |

## 10. Known limits

* Rate limits and lockout counters are in memory (fine for one server process; use Redis for several).
* FAISS indexes are files on the server's disk and are loaded by one process; run a single uvicorn worker.
* Tables are created automatically; use Alembic for schema changes in production.
* No OCR for scanned PDFs. DOCX table text is appended after the paragraphs.
