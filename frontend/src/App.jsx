import { useCallback, useEffect, useState } from "react";
import { api, onUnauthorized } from "./api";
import { isTokenExpired, startIdleTimer, tokenStore } from "./security";
import AuthPage from "./components/AuthPage";
import FileUpload from "./components/FileUpload";
import DocumentList from "./components/DocumentList";
import Chat from "./components/Chat";
import ApiTokens from "./components/ApiTokens";
import AdminPanel from "./components/AdminPanel";

const IDLE_MINUTES = 30;

export default function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [notice, setNotice] = useState("");
  const [view, setView] = useState("chat"); // "chat" | "tokens" | "admin"
  const [docs, setDocs] = useState([]);
  const [messages, setMessages] = useState([]); // the conversation lives here, in the browser
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "light";
    const saved = window.localStorage.getItem("document-qa-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("document-qa-theme", theme);
  }, [theme]);

  const logout = useCallback((reason = "") => {
    tokenStore.clear();
    setUser(null);
    setDocs([]);
    setMessages([]); // never leave one person's conversation on screen for the next
    setView("chat");
    setNotice(typeof reason === "string" ? reason : "");
  }, []);

  const refreshDocs = useCallback(async () => {
    try {
      setDocs(await api.listDocuments());
    } catch {
      /* a 401 is handled by onUnauthorized; other errors leave the old list in place */
    }
  }, []);

  // The API client calls this when the server rejects our token.
  useEffect(() => {
    onUnauthorized(() => logout("Your session expired. Please sign in again."));
  }, [logout]);

  // Restore a session that is still valid (e.g. after a page refresh).
  useEffect(() => {
    const token = tokenStore.get();
    if (!token || isTokenExpired(token)) {
      tokenStore.clear();
      setBooting(false);
      return;
    }
    api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setBooting(false));
  }, []);

  // While signed in: load documents, watch for token expiry and inactivity.
  useEffect(() => {
    if (!user) return undefined;
    refreshDocs();
    const stopIdle = startIdleTimer(() => logout(`Signed out after ${IDLE_MINUTES} minutes of inactivity.`), IDLE_MINUTES);
    const expiry = setInterval(() => {
      const token = tokenStore.get();
      if (!token || isTokenExpired(token)) logout("Your session expired. Please sign in again.");
    }, 15000);
    return () => {
      stopIdle();
      clearInterval(expiry);
    };
  }, [user, refreshDocs, logout]);

  function handleAuth(data) {
    tokenStore.set(data.access_token);
    setNotice("");
    setUser(data.user);
  }

  if (booting) return <div className="boot">Loading…</div>;
  if (!user) return <AuthPage onAuth={handleAuth} notice={notice} />;

  const isAdmin = user.role === "admin";
  const tab = (id, label) => (
    <button className={view === id ? "tab active" : "tab"} onClick={() => setView(id)} aria-current={view === id ? "page" : undefined}>
      {label}
    </button>
  );

  return (
    <div className={`app${user.role === "admin" ? " admin-user" : ""}`}>
      <header className="topbar">
        <div className="brand">Document Q&amp;A</div>
        <nav className="tabs" aria-label="Main">
          {tab("chat", "Chat")}
          {tab("tokens", "API access")}
          {isAdmin && tab("admin", "Admin")}
        </nav>
        <div className="who">
          <button
            type="button"
            className="btn btn-quiet theme-toggle"
            onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
          </button>
          <span className={`badge badge-${user.role}`}>{user.role}</span>
          <span className="who-name">{user.name}</span>
          <button className="btn btn-quiet" onClick={() => logout()}>Sign out</button>
        </div>
      </header>

      <main>
        {view === "chat" && (
          <div className="workspace">
            <aside className="sidebar">
              <FileUpload onUploaded={refreshDocs} />
              <DocumentList
                docs={docs}
                onChanged={refreshDocs}
                onClearedAll={() => setMessages([])}
              />
            </aside>
            <Chat docs={docs} messages={messages} setMessages={setMessages} />
          </div>
        )}
        {view === "tokens" && <ApiTokens />}
        {view === "admin" && isAdmin && <AdminPanel currentUserId={user.id} />}
      </main>
    </div>
  );
}
