/** Where an answer came from. These values come from the server's database, never from the AI's own words. */
export default function Sources({ sources }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="sources">
      <span className="sources-label">Sources</span>
      <ul>
        {sources.map((s, i) => (
          <li key={`${s.filename}-${s.page}-${i}`}>
            <mark>{s.filename}{s.page ? `, page ${s.page}` : ""}</mark>
          </li>
        ))}
      </ul>
    </div>
  );
}
