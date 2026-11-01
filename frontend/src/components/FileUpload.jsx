import { useRef, useState } from "react";
import { uploadDocument } from "../api";
import { MAX_UPLOAD_MB, validateFile } from "../security";

const STATUS_TEXT = {
  queued: "Waiting…",
  uploading: "Uploading",
  processing: "Reading and indexing…",
};

export default function FileUpload({ onUploaded }) {
  const [items, setItems] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  const patch = (id, changes) => setItems((list) => list.map((i) => (i.id === id ? { ...i, ...changes } : i)));

  async function handleFiles(fileList) {
    const files = Array.from(fileList);
    if (!files.length || busy) return;
    setBusy(true);
    const stamp = Date.now();
    const entries = files.map((file, n) => ({ id: `${stamp}-${n}`, file }));
    setItems(entries.map(({ id, file }) => ({ id, name: file.name, status: "queued", progress: 0, message: "" })));

    for (const { id, file } of entries) {
      const problem = validateFile(file);
      if (problem) {
        patch(id, { status: "error", message: problem });
        continue;
      }
      patch(id, { status: "uploading" });
      try {
        const doc = await uploadDocument(file, (pct) =>
          patch(id, pct >= 100 ? { status: "processing", progress: 100 } : { progress: pct })
        );
        patch(id, { status: "done", message: `Added. ${doc.chunk_count} text chunks extracted.` });
        onUploaded?.();
      } catch (err) {
        patch(id, { status: "error", message: err.message });
      }
    }
    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <section className="panel">
      <h2>Your documents</h2>
      <div
        className={dragging ? "dropzone dragging" : "dropzone"}
        role="button"
        tabIndex={0}
        aria-label="Choose files to upload"
        onClick={() => !busy && inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), !busy && inputRef.current?.click())}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
      >
        <strong>{busy ? "Uploading…" : "Drop files here or click to choose"}</strong>
        <span>PDF, DOCX or TXT, up to {MAX_UPLOAD_MB} MB each</span>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          multiple
          hidden
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      <ul className="upload-list" aria-live="polite">
        {items.map((i) => (
          <li key={i.id} className={`upload upload-${i.status}`}>
            <span className="upload-name">{i.name}</span>
            {(i.status === "uploading" || i.status === "processing") && (
              <progress max="100" value={i.status === "processing" ? undefined : i.progress} />
            )}
            <span className="upload-msg">
              {i.message || `${STATUS_TEXT[i.status]}${i.status === "uploading" ? ` ${i.progress}%` : ""}`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
