/** Every call to the backend goes through this file. The browser only ever holds a login token. */
import { tokenStore } from "./security";

export const API_BASE = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

let unauthorizedHandler = () => {};
/** App registers a function that signs the user out when the server says the token is no longer valid. */
export const onUnauthorized = (fn) => {
  unauthorizedHandler = fn;
};

const OFFLINE = "Can't reach the server. Make sure the backend is running.";

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    });
  } catch {
    throw new ApiError(OFFLINE, 0);
  }

  let data = null;
  try { data = await res.json(); } catch { /* 204 or empty body */ }

  if (!res.ok) {
    if (res.status === 401 && token) unauthorizedHandler();
    throw new ApiError(data?.detail || `Something went wrong (error ${res.status}).`, res.status);
  }
  return data;
}

/** Upload with progress. fetch() cannot report upload progress, so this uses XMLHttpRequest. */
export function uploadDocument(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API_BASE + "/api/upload");
    const token = tokenStore.get();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data);
      if (xhr.status === 401 && token) unauthorizedHandler();
      reject(new ApiError(data?.detail || `Upload failed (error ${xhr.status}).`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError(OFFLINE, 0));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = {
  login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password } }),
  register: (name, email, password) => request("/api/auth/register", { method: "POST", body: { name, email, password } }),
  me: () => request("/api/auth/me"),

  listDocuments: () => request("/api/documents"),
  deleteDocument: (id) => request(`/api/documents/${id}`, { method: "DELETE" }),
  clearAll: () => request("/api/clear", { method: "POST" }),
  chat: (question, conversation_history) => request("/api/chat", { method: "POST", body: { question, conversation_history } }),
  speech: async (text) => {
    const token = tokenStore.get();
    const res = await fetch(API_BASE + "/api/chat/speech", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text }),
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    });

    if (!res.ok) {
      let data = null;
      try { data = await res.json(); } catch { /* empty */ }
      throw new ApiError(data?.detail || `Speech failed (error ${res.status}).`, res.status);
    }
    return res.blob();
  },

  listTokens: () => request("/api/tokens"),
  createToken: (name) => request("/api/tokens", { method: "POST", body: { name } }),
  revokeToken: (id) => request(`/api/tokens/${id}`, { method: "DELETE" }),

  admin: {
    stats: () => request("/api/admin/stats"),
    users: () => request("/api/admin/users"),
    updateUser: (id, changes) => request(`/api/admin/users/${id}`, { method: "PATCH", body: changes }),
    deleteUser: (id) => request(`/api/admin/users/${id}`, { method: "DELETE" }),
    documents: () => request("/api/admin/documents"),
    deleteDocument: (id) => request(`/api/admin/documents/${id}`, { method: "DELETE" }),
    chatLogs: () => request("/api/admin/chat-logs?limit=100"),
  },
};
