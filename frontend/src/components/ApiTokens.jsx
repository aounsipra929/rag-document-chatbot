import { useCallback, useEffect, useState } from "react";
import { API_BASE, api } from "../api";
import { fmtDate } from "../format";

export default function ApiTokens() {
  const [tokens, setTokens] = useState([]);
  const [name, setName] = useState("");
  const [created, setCreated] = useState(null); // shown once, then discarded
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try { setTokens(await api.listTokens()); } catch (err) { setError(err.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      setCreated(await api.createToken(name));
      setName("");
      setCopied(false);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function revoke(t) {
    if (!window.confirm(`Revoke "${t.name}"? Anything using it will stop working.`)) return;
    try { await api.revokeToken(t.id); load(); } catch (err) { setError(err.message); }
  }

  async function copy() {
    try { await navigator.clipboard.writeText(created.token); setCopied(true); } catch { setError("Copy failed. Select the token and copy it manually."); }
  }

  const base = API_BASE || window.location.origin;

  return (
    <div className="page">
      <h1>API access</h1>
      <p className="lead">
        Use an API token to ask questions about your documents from your own scripts or apps. Tokens can ask
        questions and list documents. They can't upload, delete or change anything.
      </p>
      {error && <p className="banner banner-error" role="alert">{error}</p>}

      <form className="inline-form" onSubmit={create}>
        <label>Token name
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="For example: HR bot" />
        </label>
        <button className="btn btn-primary" disabled={!name.trim()}>Create token</button>
      </form>

      {created && (
        <div className="banner banner-ok" role="status">
          <p><strong>Copy your token now.</strong> You won't be able to see it again.</p>
          <code className="token">{created.token}</code>
          <button className="btn btn-small" onClick={copy}>{copied ? "Copied" : "Copy token"}</button>
        </div>
      )}

      <h2>Your tokens</h2>
      {tokens.length === 0 ? (
        <p className="empty">You haven't created any tokens.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Starts with</th><th>Created</th><th>Last used</th><th /></tr></thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td><code>{t.prefix}…</code></td>
                  <td>{fmtDate(t.created_at)}</td>
                  <td>{fmtDate(t.last_used_at)}</td>
                  <td><button className="btn btn-quiet btn-small" onClick={() => revoke(t)}>Revoke</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Example request</h2>
      <pre className="code">{`curl -X POST ${base}/api/chat \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"question": "What is the annual leave policy?"}'`}</pre>
      <p className="hint">The response looks like: {`{ "answer": "…", "sources": [{ "filename": "handbook.pdf", "page": 4 }] }`}</p>
    </div>
  );
}
