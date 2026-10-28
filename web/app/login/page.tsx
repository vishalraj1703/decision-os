"use client";

import { signIn } from "next-auth/react";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";
import "./login.css";

interface P { name: string; email: string; team: string; role: string }

// Each note sentence sits on the same row as the task it produces.
const ROWS = [
  { note: "Raj said the payment API will be ready by Friday.", task: "Build the payment API", who: "R", owner: "Raj", due: "Fri 30 Oct", ok: "On track", slip: "Late", tone: "bad" },
  { note: "Priya will test it once Raj finishes.", task: "Test the payment API", who: "P", owner: "Priya", due: "After Raj", ok: "Waiting", slip: "At risk", tone: "warn" },
  { note: "Someone needs to follow up with finance.", task: "Follow up with finance", who: "?", owner: "Owner not stated", due: "No date", ok: "Ask", slip: "Ask", tone: "ask" },
];
// step 0: notes only · 1–3: rows found one by one · 4: slip predicted · 5: hold
const STEP_MS = [1400, 900, 900, 1300, 3200, 1200];

function useStep() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setStep(4); return; }
    const t = window.setTimeout(() => setStep((s) => (s + 1) % STEP_MS.length), STEP_MS[step]);
    return () => window.clearTimeout(t);
  }, [step]);
  return step;
}

function Demo() {
  const step = useStep();
  const slipped = step >= 4;
  return (
    <div className="lg-demo" aria-hidden="true">
      <div className="lg-demo-head">
        <span>Monday project sync</span>
        <span className={`lg-demo-state${slipped ? " is-warn" : ""}`}>
          {step === 0 ? "Notes pasted" : step < 4 ? "Finding tasks…" : "Delay predicted"}
        </span>
      </div>
      <div className="lg-cols"><span>From the notes</span><span /><span>Task created</span></div>
      {ROWS.map((r, i) => {
        const found = step > i;
        const status = slipped ? r.slip : r.ok;
        return (
          <div key={r.task} className={`lg-row${found ? " is-found" : ""}${step === i + 1 ? " is-reading" : ""}`}>
            <p className="lg-quote">{r.note}</p>
            <span className="lg-arrow-r">→</span>
            <div className={`lg-task${slipped && r.tone !== "ask" ? ` is-${r.tone}` : ""}`}>
              <div className="lg-task-line">
                <b>{r.task}</b>
                <span className={`lg-chip ${r.tone === "ask" ? "c-ask" : slipped ? `c-${r.tone}` : r.tone === "warn" ? "c-wait" : "c-ok"}`}>{status}</span>
              </div>
              <div className="lg-task-meta">
                <span className={`lg-av${r.who === "?" ? " is-empty" : ""}`}>{r.who}</span>{r.owner} · {r.due}
              </div>
            </div>
          </div>
        );
      })}
      <div className={`lg-warn${slipped ? " is-on" : ""}`}>
        <Icon name="alert" size={14} />If Raj is late, Priya’s testing slips too. Both are told today.
      </div>
    </div>
  );
}

export default function Login() {
  const [people, setPeople] = useState<P[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shake, setShake] = useState(0);
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
    else { setError("That password didn't work."); setShake((n) => n + 1); }
  }

  const managers = people.filter((p) => p.role === "manager");
  const team = people.filter((p) => p.role !== "manager");
  const me = people.find((p) => p.email === email);

  return (
    <div className="lg">
      <section className="lg-story">
        <header className="lg-brand">
          <span className="lg-mark"><Icon name="split" size={15} strokeWidth={2.2} /></span>
          <span className="lg-name">Decision OS</span>
          <span className="lg-event">Infosys IGNITE · Hack-AI-Thon 2026 · EP-01</span>
        </header>

        <div className="lg-copy">
          <h1>Meetings end.<br />The work shouldn’t get lost.</h1>
          <p>Paste your meeting notes. Decision OS lists who does what and by when, shows the line each task came from, and warns you before a deadline slips.</p>
        </div>

        <Demo />

        <ul className="lg-points">
          <li><Icon name="quote" size={15} /><span><b>Shows proof.</b> Every task links to its sentence.</span></li>
          <li><Icon name="help" size={15} /><span><b>Never guesses.</b> Missing owner? It asks.</span></li>
          <li><Icon name="clock" size={15} /><span><b>Warns early.</b> Delays flagged before the date.</span></li>
        </ul>

        <footer className="lg-foot">AI runs on Qualcomm Cloud AI Playground (Llama 3.3 70B)</footer>
      </section>

      <section className="lg-side">
        <form key={shake} className={`lg-form${shake ? " lg-shake" : ""}`} onSubmit={submit}>
          <div>
            <h2>Sign in</h2>
            <p className="lg-help">Use a demo account to see your team’s board.</p>
          </div>

          <div className="lg-who">
            <span className={`lg-who-av${me?.role === "manager" ? " is-mgr" : ""}`}>{me?.name?.[0] ?? "·"}</span>
            <div>
              <b>{me?.name ?? "Loading accounts…"}</b>
              <span>{me ? (me.role === "manager" ? "Manager · sees every team" : `${me.team} · sees own tasks`) : ""}</span>
            </div>
          </div>

          <div className="lg-field">
            <label htmlFor="who">Account</label>
            <select id="who" value={email} onChange={(e) => setEmail(e.target.value)}>
              {managers.length > 0 && <optgroup label="Managers">{managers.map((p) => <option key={p.email} value={p.email}>{p.name}</option>)}</optgroup>}
              {team.length > 0 && <optgroup label="Team">{team.map((p) => <option key={p.email} value={p.email}>{p.name} · {p.team}</option>)}</optgroup>}
            </select>
          </div>

          <div className="lg-field">
            <label htmlFor="pw">Password</label>
            <div className="lg-pw">
              <input id="pw" type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                     autoComplete="current-password" placeholder="Demo password" />
              <button type="button" className="lg-eye" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />
                  {show && <path d="M3 3l18 18" />}
                </svg>
              </button>
            </div>
          </div>

          {error && <div className="lg-error" role="alert"><Icon name="alert" size={15} />{error}</div>}

          <button className="lg-submit" type="submit" disabled={busy || !email || !password}>
            {busy ? <><span className="spinner" />Signing in…</> : "Sign in"}
          </button>

          <p className="lg-small">Demo access for Hack-AI-Thon judges. Ask the team for the password.</p>
        </form>
      </section>
    </div>
  );
}
