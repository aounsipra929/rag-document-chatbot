import { useState } from "react";
import { api } from "../api";
import { fmtSize } from "../format";

export default function DocumentList({ docs, onChanged, onClearedAll }) {
  const [error, setError] = useState("");

  async function remove(doc) {
    if (!window.confirm(`Remove "${doc.filename}"? Its text and search data will be deleted.`)) return;
    setError("");
    try {
      await api.deleteDocument(doc.id);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeAll() {
    if (!window.confirm("Remove all your documents? This cannot be undone.")) return;
    setError("");
    try {
      await api.clearAll();
      onChanged();
      onClearedAll();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h3>Uploaded ({docs.length})</h3>
        {docs.length > 0 && <button className="btn btn-quiet btn-small" onClick={removeAll}>Remove all</button>}
      </div>
      {error && <p className="banner banner-error" role="alert">{error}</p>}
      {docs.length === 0 ? (
        <p className="empty">No documents yet. Add one above to start asking questions.</p>
      ) : (
        <ul className="doc-list">
          {docs.map((d) => (
            <li key={d.id}>
              <div>
                <span className="doc-name" title={d.filename}>{d.filename}</span>
                <span className="doc-meta">{d.chunk_count} chunks, {fmtSize(d.size_bytes)}</span>
              </div>
              <button className="btn btn-quiet btn-small" onClick={() => remove(d)} aria-label={`Remove ${d.filename}`}>Remove</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
