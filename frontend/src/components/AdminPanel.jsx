import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { fmtDate, fmtSize } from "../format";

/** Loads data with loading + error state, and lets the caller refresh it. */
function useLoad(fn) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const load = useCallback(async () => {
    try {
      setState({ data: await fn(), error: "", loading: false });
    } catch (err) {
      setState({ data: null, error: err.message, loading: false });
    }
  }, [fn]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}

function Status({ loading, error }) {
  if (loading) return <p className="empty">Loading…</p>;
  if (error) return <p className="banner banner-error" role="alert">{error}</p>;
  return null;
}

function Overview() {
  const { data, error, loading } = useLoad(api.admin.stats);
  if (!data) return <Status loading={loading} error={error} />;
  const answeredPct = data.questions_total ? Math.round((data.questions_answered / data.questions_total) * 100) : 0;
  const stats = [
    [data.total_users, `Users (${data.active_users} active, ${data.admins} admin)`],
    [data.total_documents, "Documents"],
    [data.total_chunks, "Searchable text chunks"],
    [data.questions_total, `Questions asked (${data.questions_last_7_days} in the last 7 days)`],
    [`${answeredPct}%`, `Answered from documents (${data.questions_not_found} not found)`],
  ];
  return (
    <dl className="stats">
      {stats.map(([value, label]) => (
        <div key={label}><dd>{value}</dd><dt>{label}</dt></div>
      ))}
    </dl>
  );
}

function Users({ currentUserId }) {
  const { data, error, loading, reload } = useLoad(api.admin.users);
  const [actionError, setActionError] = useState("");

  async function run(action) {
    setActionError("");
    try { await action(); reload(); } catch (err) { setActionError(err.message); }
  }
  if (!data) return <Status loading={loading} error={error} />;

  return (
    <>
      {actionError && <p className="banner banner-error" role="alert">{actionError}</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Docs</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {data.map((u) => {
              const self = u.id === currentUserId;
              return (
                <tr key={u.id}>
                  <td>{u.name}{self && <span className="hint"> (you)</span>}</td>
                  <td>{u.email}</td>
                  <td>
                    <select
                      value={u.role}
                      disabled={self}
                      aria-label={`Role for ${u.email}`}
                      onChange={(e) => run(() => api.admin.updateUser(u.id, { role: e.target.value }))}
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td>{u.is_active ? "Active" : "Deactivated"}</td>
                  <td>{u.document_count}</td>
                  <td>{fmtDate(u.last_login_at)}</td>
                  <td className="actions">
                    <button className="btn btn-quiet btn-small" disabled={self} onClick={() => run(() => api.admin.updateUser(u.id, { is_active: !u.is_active }))}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                    <button
                      className="btn btn-quiet btn-small btn-danger"
                      disabled={self}
                      onClick={() => window.confirm(`Delete ${u.email} and all of their documents?`) && run(() => api.admin.deleteUser(u.id))}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Documents() {
  const { data, error, loading, reload } = useLoad(api.admin.documents);
  const [actionError, setActionError] = useState("");
  if (!data) return <Status loading={loading} error={error} />;

  async function remove(d) {
    if (!window.confirm(`Delete "${d.filename}" owned by ${d.owner_email}?`)) return;
    try { await api.admin.deleteDocument(d.id); reload(); } catch (err) { setActionError(err.message); }
  }

  return (
    <>
      <p className="hint">Admins can see which documents exist, but not what is inside them.</p>
      {actionError && <p className="banner banner-error" role="alert">{actionError}</p>}
      {data.length === 0 ? <p className="empty">No documents have been uploaded.</p> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>File</th><th>Owner</th><th>Chunks</th><th>Size</th><th>Uploaded</th><th /></tr></thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id}>
                  <td>{d.filename}</td><td>{d.owner_email}</td><td>{d.chunk_count}</td>
                  <td>{fmtSize(d.size_bytes)}</td><td>{fmtDate(d.created_at)}</td>
                  <td><button className="btn btn-quiet btn-small btn-danger" onClick={() => remove(d)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Activity() {
  const { data, error, loading } = useLoad(api.admin.chatLogs);
  if (!data) return <Status loading={loading} error={error} />;
  if (data.length === 0) return <p className="empty">No questions have been asked yet.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>When</th><th>User</th><th>Question</th><th>Result</th><th>Best match</th><th>Via</th></tr></thead>
        <tbody>
          {data.map((l) => (
            <tr key={l.id}>
              <td>{fmtDate(l.created_at)}</td><td>{l.user_email}</td><td className="wrap">{l.question}</td>
              <td>{l.answered ? "Answered" : "Not found"}</td>
              <td>{l.top_score == null ? "None" : l.top_score.toFixed(2)}</td>
              <td>{l.channel}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SECTIONS = [
  ["overview", "Overview"],
  ["users", "Users"],
  ["documents", "Documents"],
  ["activity", "Activity"],
];

export default function AdminPanel({ currentUserId }) {
  const [section, setSection] = useState("overview");
  return (
    <div className="page">
      <h1>Administration</h1>
      <div className="subtabs" role="tablist">
        {SECTIONS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={section === id} className={section === id ? "subtab active" : "subtab"} onClick={() => setSection(id)}>
            {label}
          </button>
        ))}
      </div>
      {section === "overview" && <Overview />}
      {section === "users" && <Users currentUserId={currentUserId} />}
      {section === "documents" && <Documents />}
      {section === "activity" && <Activity />}
    </div>
  );
}
