"use client";

import { signIn } from "next-auth/react";
import { useEffect, useState } from "react";

interface P { name: string; email: string; team: string; role: string }

export default function Login() {
  const [people, setPeople] = useState<P[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/people").then(async (r) => {
      const d = await r.json();
      if (!r.ok) { setError(d.message); return; }
      setPeople(d);
      setEmail(d[0]?.email ?? "");
    }).catch(() => setError("Cannot reach the server."));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await signIn("credentials", { email, password, redirect: false });
    setBusy(false);
    if (r?.ok) window.location.href = "/";
    else setError("Sign-in failed. Check the demo password in your .env files.");
  }

  return (
    <div className="login card">
      <div className="brand" style={{ marginBottom: 18 }}><span className="brand-mark">DO</span>Decision OS</div>
      <h1>Sign in</h1>
      <p className="muted">Demo accounts: one manager and the team. Managers see the whole graph; employees see only their tasks.</p>
      <form onSubmit={submit} className="stack">
        <div>
          <label htmlFor="who">Account</label>
          <select id="who" value={email} onChange={(e) => setEmail(e.target.value)}>
            {people.map((p) => <option key={p.email} value={p.email}>{p.name} · {p.role === "manager" ? "Manager" : p.team}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="pw">Demo password</label>
          <input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </div>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <button className="btn-gold" type="submit" disabled={busy || !email || !password}>{busy ? "Signing in..." : "Sign in"}</button>
      </form>
    </div>
  );
}
