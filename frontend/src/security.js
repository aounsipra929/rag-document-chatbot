/**
 * Client-side security helpers.
 *
 * These checks make the app safer and friendlier, but a browser can always be bypassed:
 * the SERVER re-checks every rule (auth, roles, file type/size, input length).
 *
 * Design choices:
 *  - The login token lives in sessionStorage (cleared when the tab closes), never in localStorage
 *    or a cookie, and it expires after ACCESS_TOKEN_MINUTES on the server.
 *  - The app never uses dangerouslySetInnerHTML: answers are rendered as plain text, so a
 *    malicious document cannot inject script into the page.
 *  - The OpenAI key does not exist in the browser at all.
 */

// ---------------------------------------------------------------- token storage
const TOKEN_KEY = "docqa.token";

export const tokenStore = {
  get() {
    try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token) {
    try { sessionStorage.setItem(TOKEN_KEY, token); } catch { /* storage blocked: user must sign in again */ }
  },
  clear() {
    try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

/** Read the (unverified) payload of a JWT. Only used to know when it expires; the server does the real check. */
export function decodeJwt(token) {
  try {
    const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, "=")));
  } catch {
    return null;
  }
}

export function isTokenExpired(token, skewSeconds = 10) {
  const payload = decodeJwt(token);
  return !payload || !payload.exp || payload.exp * 1000 - skewSeconds * 1000 <= Date.now();
}

// ---------------------------------------------------------------- input validation (mirrors the server)
export const MAX_UPLOAD_MB = 10; // keep in sync with MAX_UPLOAD_MB in the backend .env
export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"];
export const MAX_QUESTION_CHARS = 2000;

export function validateFile(file) {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Unsupported file type. Use PDF, DOCX or TXT.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `This file is larger than ${MAX_UPLOAD_MB} MB.`;
  return null;
}

export function validateEmail(email) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim()) ? null : "Enter a valid email address.";
}

export function validatePassword(password) {
  if (password.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return "Password must contain a letter and a number.";
  return null;
}

export function validateQuestion(question) {
  if (!question.trim()) return "Please type a question.";
  if (question.length > MAX_QUESTION_CHARS) return `Your question is over ${MAX_QUESTION_CHARS} characters.`;
  return null;
}

// ---------------------------------------------------------------- idle sign-out
/** Calls onIdle after `minutes` without mouse, keyboard or touch activity. Returns a function that stops it. */
export function startIdleTimer(onIdle, minutes = 30) {
  const events = ["mousemove", "keydown", "click", "touchstart", "scroll"];
  let timer;
  const reset = () => {
    clearTimeout(timer);
    timer = setTimeout(onIdle, minutes * 60 * 1000);
  };
  events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
  reset();
  return () => {
    clearTimeout(timer);
    events.forEach((e) => window.removeEventListener(e, reset));
  };
}
