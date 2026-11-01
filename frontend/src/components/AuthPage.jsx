import { useState } from "react";
import { api } from "../api";
import { validateEmail, validatePassword } from "../security";

export default function AuthPage({ onAuth, notice }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const registering = mode === "register";

  async function submit(e) {
    e.preventDefault();
    setError("");
    const problem =
      (registering && !name.trim() ? "Enter your name." : null) ||
      validateEmail(email) ||
      (registering ? validatePassword(password) : password ? null : "Enter your password.");
    if (problem) return setError(problem);

    setBusy(true);
    try {
      const data = registering ? await api.register(name.trim(), email, password) : await api.login(email, password);
      setPassword("");
      onAuth(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-intro">
        <h1>Ask your documents. Get answers you can check.</h1>
        <p>
          Upload PDF, Word or text files, then ask questions. Every answer comes only from your files and shows the
          page it came from. If the answer isn't there, you'll be told so.
        </p>
      </section>

      <form className="auth-card" onSubmit={submit} noValidate>
        <h2>{registering ? "Create your account" : "Sign in"}</h2>
        {notice && <p className="banner banner-info" role="status">{notice}</p>}
        {error && <p className="banner banner-error" role="alert">{error}</p>}

        {registering && (
          <label>Name
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={100} />
          </label>
        )}
        <label>Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" maxLength={255} />
        </label>
        <label>Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={registering ? "new-password" : "current-password"}
            maxLength={128}
          />
          {registering && <span className="hint">At least 8 characters, with a letter and a number.</span>}
        </label>

        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Please wait…" : registering ? "Create account" : "Sign in"}
        </button>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => { setMode(registering ? "login" : "register"); setError(""); }}
        >
          {registering ? "I already have an account" : "Create an account"}
        </button>
      </form>
    </div>
  );
}
