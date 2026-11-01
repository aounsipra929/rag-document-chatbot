# Security

## Server side (`backend/`)

| Protection | Where |
|------------|-------|
| Passwords hashed with bcrypt (12 rounds, SHA-256 pre-hash for long passwords) | `security.py` |
| Same error and timing for unknown email vs wrong password | `routers/auth.py` |
| Account lockout: 5 failed sign-ins locks for 15 minutes | `routers/auth.py` |
| Password rules: 8+ characters, a letter and a number | `schemas.py` |
| Short-lived JWT login tokens; role is re-read from the database on every request, so demotions and deactivations apply immediately | `security.py`, `deps.py` |
| API tokens: random, hashed (SHA-256) at rest, shown once, limited to chat and listing documents | `security.py`, `deps.py` |
| Role checks on every admin route (`require_admin`); admins cannot demote, deactivate or delete themselves | `deps.py`, `routers/admin.py` |
| Per-user isolation: one FAISS index per user; every chunk lookup also checks `Document.user_id`; other users' documents return 404 | `vector_store.py`, `qa_service.py`, `routers/documents.py` |
| Rate limits: login 10/min per IP, sign-up 5/hour per IP, chat 30/min and upload 10/min per user | `security.py` |
| Uploads: extension allow-list, size cap, magic-byte check, sanitised filename, per-user document cap; the original file is never stored | `routers/documents.py`, `document_loader.py` |
| Prompt-injection resistance: document text is labelled untrusted; the model cannot choose its own citations | `qa_service.py` |
| Security headers (nosniff, frame deny, no-referrer, no-store, CSP, HSTS in production) and request-size guard | `SecurityHeadersMiddleware` |
| CORS: explicit origin list, no wildcard, no cookies | `main.py` |
| OpenAPI docs disabled when `APP_ENV=production` | `main.py` |
| Secrets only in `.env` (git-ignored); startup fails if `JWT_SECRET` is weak | `config.py` |
| Errors show friendly messages; details are logged, not returned | `main.py` |

## Client side (`frontend/`)

| Protection | Where |
|------------|-------|
| Token kept in `sessionStorage` (gone when the tab closes), never in `localStorage` or URLs | `security.js` |
| Auto sign-out on token expiry, on a 401 from the server, and after 30 minutes idle; chat and documents are wiped from memory on sign-out | `App.jsx`, `security.js` |
| No `dangerouslySetInnerHTML`: answers and filenames render as text, so document content cannot inject script | `Message.jsx` |
| Production Content-Security-Policy (own scripts only, connections only to self and the backend) | `vite.config.js`, `public/_headers` |
| No third-party scripts, fonts or trackers | whole app |
| Input checks (file type/size, password rules, question length) for fast feedback | `security.js` |
| `credentials: "omit"`, `no-referrer`, `no-store` on API calls | `api.js` |
| Admin tab is hidden for non-admins, but this is only cosmetic: the server enforces roles | `App.jsx`, `deps.py` |
| The OpenAI key never exists in browser code. Do not put secrets in `VITE_*` variables | `.env.example` |

## Before you deploy

1. Set `APP_ENV=production`, a strong `JWT_SECRET`, and `CORS_ORIGINS` to your real frontend URL.
2. Serve both sides over HTTPS (a reverse proxy such as nginx or Caddy) and limit request body size there too.
3. Update `connect-src` in `frontend/public/_headers` to your backend URL, and set `VITE_API_URL` before `npm run build`.
4. Change or remove the seeded admin password after first sign-in; consider `ALLOW_REGISTRATION=false` for private use.
5. Use PostgreSQL and back up `backend/data/`. Run a single backend worker (FAISS files and in-memory rate limits).
6. Admins can read question text in Admin → Activity. If that does not fit your privacy policy, remove the `question` column from `ChatLogOut`.

## Reporting a vulnerability

Open a private issue or contact the project owner directly. Please do not post details publicly first.
