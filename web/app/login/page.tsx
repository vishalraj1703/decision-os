"use client";

import { signIn } from "next-auth/react";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";

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
    }).catch(() => setError("Can't reach the server."));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await signIn("credentials", { email, password, redirect: false });
    setBusy(false);
    if (r?.ok) window.location.href = "/";
    else setError("That password didn't work.");
  }

  const managers = people.filter((p) => p.role === "manager");
  const team = people.filter((p) => p.role !== "manager");

  return (
    <div className="auth">
      <div className="auth-side">
        <div className="logo" style={{ padding: 0 }}><span className="logo-mark"><Icon name="split" size={14} strokeWidth={2.2} /></span>Decision OS</div>
        <h1>Every decision from every meeting, with an owner and a source.</h1>
        <p>Paste your meeting notes. Decision OS turns them into tasks, owners, deadlines and dependencies, and tells you what's about to slip.</p>
        <div className="auth-points">
          <div><Icon name="help" /><span>If the notes don't say who owns something, it says so instead of guessing.</span></div>
          <div><Icon name="quote" /><span>Every item links back to the exact sentence it came from.</span></div>
          <div><Icon name="split" /><span>Catches decisions that quietly reverse last week's.</span></div>
          <div><Icon name="clock" /><span>When a deadline slips, everyone downstream finds out first.</span></div>
        </div>
        <div className="tiny faint">AI inference on Qualcomm Cloud AI Playground</div>
      </div>
      <div className="auth-form">
        <form onSubmit={submit}>
          <div>
            <h1 style={{ fontSize: 22 }}>Sign in</h1>
            <p className="small muted" style={{ marginTop: 4 }}>Choose a demo account. Managers see the whole team; everyone else sees their own work.</p>
          </div>
          <div>
            <label className="label" htmlFor="who">Account</label>
            <select id="who" className="select" value={email} onChange={(e) => setEmail(e.target.value)} style={{ height: 38 }}>
              {managers.length > 0 && <optgroup label="Managers">{managers.map((p) => <option key={p.email} value={p.email}>{p.name}</option>)}</optgroup>}
              {team.length > 0 && <optgroup label="Team">{team.map((p) => <option key={p.email} value={p.email}>{p.name} · {p.team}</option>)}</optgroup>}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="pw">Password</label>
            <input id="pw" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" style={{ height: 38 }} />
          </div>
          {error && <div className="alert alert-error" role="alert"><Icon name="alert" size={15} />{error}</div>}
          <button className="btn btn-primary" type="submit" disabled={busy || !email || !password} style={{ height: 38, justifyContent: "center" }}>
            {busy ? <><span className="spinner" />Signing in…</> : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
