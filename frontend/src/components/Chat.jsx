import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { MAX_QUESTION_CHARS, tokenStore, validateQuestion } from "../security";
import { getSpeechRecognitionCtor, speakText, stopListening, stopSpeaking } from "../voice";
import Message from "./Message";

let nextId = 0;
const newId = () => `m${++nextId}`;

export default function Chat({ docs, messages, setMessages }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [speakingId, setSpeakingId] = useState(null);
  const endRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioRef = useRef(null);
  const recognitionRef = useRef(null);
  const hasDocs = docs.length > 0;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  useEffect(() => () => {
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopListening(recognitionRef.current);
    stopSpeaking();
    audioRef.current?.pause();
  }, []);

  function cancelPlayback() {
    audioRef.current?.pause();
    audioRef.current = null;
    stopSpeaking();
    setSpeakingId(null);
  }

  function buildHistory() {
    return messages
      .filter((m) => !m.isError)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content.slice(0, 1000) }));
  }

  async function submitQuestion(question, { useInput = false } = {}) {
    if (loading) return;
    const finalQuestion = (useInput ? input : question).trim();
    if (!finalQuestion) return;

    const problem = validateQuestion(finalQuestion);
    if (problem) {
      setError(finalQuestion ? problem : "");
      return;
    }

    cancelPlayback();
    setError("");
    const history = buildHistory();
    setMessages((prev) => [...prev, { id: newId(), role: "user", content: finalQuestion }]);
    if (useInput) setInput("");
    setLoading(true);
    try {
      const res = await api.chat(finalQuestion, history);
      setMessages((prev) => [...prev, { id: newId(), role: "assistant", content: res.answer, sources: res.sources }]);
    } catch (err) {
      setMessages((prev) => [...prev, { id: newId(), role: "assistant", content: err.message, isError: true }]);
    } finally {
      setLoading(false);
    }
  }

  async function send() {
    await submitQuestion(input, { useInput: true });
  }

  async function handleMicInput() {
    if (loading || isRecording || isTranscribing) return;

    const SpeechRecognitionCtor = getSpeechRecognitionCtor();
    if (!navigator.mediaDevices?.getUserMedia && !SpeechRecognitionCtor) {
      setError("Microphone input is not supported in this browser.");
      return;
    }

    if (SpeechRecognitionCtor) {
      stopListening(recognitionRef.current);
      const recognition = new SpeechRecognitionCtor();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";
      recognition.maxAlternatives = 1;
      recognitionRef.current = recognition;

      let finalText = "";
      recognition.onstart = () => {
        setError("");
        setIsRecording(true);
      };

      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map((result) => result[0]?.transcript || "")
          .join(" ")
          .trim();
        if (transcript) {
          finalText = transcript;
          setInput(transcript);
        }
      };

      recognition.onerror = (event) => {
        const message = event.error === "not-allowed" ? "Microphone permission was denied." : event.error === "no-speech" ? "No speech was detected. Try again." : "Voice input failed. Please try again.";
        setError(message);
        setIsRecording(false);
      };

      recognition.onend = async () => {
        setIsRecording(false);
        const trimmed = finalText.trim();
        if (!trimmed) {
          setError("No speech was detected.");
          return;
        }
        setInput(trimmed);
        await submitQuestion(trimmed);
      };

      try {
        recognition.start();
      } catch {
        setError("The microphone is already in use. Please try again.");
        setIsRecording(false);
      }
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const chunks = [];

      recorder.ondataavailable = (event) => {
        if (event.data?.size) chunks.push(event.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setIsRecording(false);
        setIsTranscribing(true);

        try {
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const form = new FormData();
          form.append("file", blob, "voice.webm");

          const token = tokenStore.get();
          const res = await fetch(`${import.meta.env.VITE_API_URL || ""}/api/chat/transcribe`, {
            method: "POST",
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: form,
            credentials: "omit",
            cache: "no-store",
            referrerPolicy: "no-referrer",
          });

          let data = null;
          try { data = await res.json(); } catch { /* empty */ }
          if (!res.ok) throw new Error(data?.detail || "Audio transcription failed.");

          const transcript = String(data?.text || "").trim();
          if (!transcript) throw new Error("No speech was detected.");

          setInput(transcript);
          setError("");
          await submitQuestion(transcript);
        } catch (err) {
          setError(err.message || "Unable to transcribe audio.");
        } finally {
          setIsTranscribing(false);
        }
      };

      recorderRef.current = recorder;
      streamRef.current = stream;
      recorder.start();
      setError("");
      setIsRecording(true);
    } catch {
      setError("Microphone access was denied or unavailable.");
    }
  }

  function stopMic() {
    if (recognitionRef.current) {
      stopListening(recognitionRef.current);
      recognitionRef.current = null;
      setIsRecording(false);
      return;
    }
    if (!recorderRef.current || recorderRef.current.state === "inactive") return;
    recorderRef.current.stop();
  }

  async function handleSpeak(message) {
    if (!message?.content) return;

    if (speakingId === message.id) {
      cancelPlayback();
      return;
    }

    cancelPlayback();

    if ("speechSynthesis" in window) {
      setSpeakingId(message.id);
      speakText(message.content, {
        onStart: () => setSpeakingId(message.id),
        onEnd: () => {
          setSpeakingId(null);
        },
        onError: () => {
          setSpeakingId(null);
          setError("Speech playback failed in this browser.");
        },
      });
      return;
    }

    try {
      setSpeakingId(message.id);
      const blob = await api.speech(message.content);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        setSpeakingId(null);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setSpeakingId(null);
        URL.revokeObjectURL(url);
        setError("Audio playback failed.");
      };
      await audio.play();
    } catch (err) {
      setSpeakingId(null);
      setError(err.message || "Unable to play audio response.");
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  }

  return (
    <section className="chat" aria-label="Chat">
      <div className="chat-head">
        <div className="using">
          {hasDocs ? (
            <>
              <span>Answering only from {docs.length === 1 ? "1 document" : `${docs.length} documents`}:</span>
              <span className="using-names">{docs.map((d) => d.filename).join(", ")}</span>
            </>
          ) : (
            <span>No documents yet. Upload one to start.</span>
          )}
        </div>
        <button className="btn btn-quiet btn-small" onClick={() => { cancelPlayback(); setMessages([]); }} disabled={messages.length === 0}>
          Clear chat
        </button>
      </div>

      <div className="thread" aria-live="polite">
        {messages.length === 0 && (
          <div className="welcome">
            <h2>{hasDocs ? "What would you like to know?" : "Start by adding a document"}</h2>
            <p>
              Answers come only from your uploaded files, with the page they were found on. If something isn't in
              them, you'll get: “I couldn't find the answer to that in the uploaded document.”
            </p>
          </div>
        )}
        {messages.map((m) => (
          <Message
            key={m.id}
            message={m}
            onSpeak={handleSpeak}
            speakingId={speakingId}
          />
        ))}
        {loading && (
          <div className="msg msg-ai" aria-label="Searching your documents">
            <div className="bubble typing"><span /><span /><span /></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="banner banner-error" role="alert">{error}</p>}
      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={hasDocs ? "Ask a question about your documents" : "Upload a document first"}
          disabled={!hasDocs}
          rows={2}
          maxLength={MAX_QUESTION_CHARS}
          aria-label="Your question"
        />
        <button
          type="button"
          className={`btn btn-mic ${isRecording ? "is-recording" : ""}`}
          onClick={isRecording ? stopMic : handleMicInput}
          disabled={!hasDocs || loading || isTranscribing}
          aria-label={isRecording ? "Stop recording" : "Start microphone input"}
          aria-pressed={isRecording}
          title={isRecording ? "Stop recording" : "Use microphone"}
        >
          {isTranscribing ? "…" : isRecording ? "■" : "🎤"}
        </button>
        <button className="btn btn-primary" onClick={send} disabled={!hasDocs || loading || !input.trim()}>
          Send
        </button>
      </div>
    </section>
  );
}
