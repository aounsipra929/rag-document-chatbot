import Sources from "./Sources";

/** Text is rendered as plain text (React escapes it), so document content can never inject HTML or script. */
export default function Message({ message, onSpeak, speakingId }) {
  const { role, content, sources, isError } = message;
  const cls = role === "user" ? "msg msg-user" : isError ? "msg msg-ai msg-error" : "msg msg-ai";
  return (
    <div className={cls}>
      <div className="bubble">
        <p>{content}</p>
        {role === "assistant" && !isError && (
          <div className="bubble-actions">
            <button
              type="button"
              className={`btn btn-quiet btn-small ${speakingId === message.id ? "is-speaking" : ""}`}
              onClick={() => onSpeak(message)}
              aria-label={speakingId === message.id ? "Stop speaking" : "Read aloud"}
            >
              {speakingId === message.id ? "■ Stop" : "🔊 Speak"}
            </button>
            <Sources sources={sources} />
          </div>
        )}
      </div>
    </div>
  );
}
