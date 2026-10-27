"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, ClarifyDraft, fmtDate, Health, Item, Meeting, WhatIf } from "@/lib/api";
import Icon from "./Icon";

type Person = { name: string; email: string; team: string; role: string };

const PART_COLOR: Record<string, string> = { O: "#2443b8", D: "#5b74d6", V: "#1d7f54", A: "#b86e00", C: "#8b8f97" };

function healthTone(score: number) {
  return score >= 80 ? "is-green" : score >= 60 ? "is-amber" : "is-red";
}

/** Fourth metric tile: the latest meeting's Health Score. Click for the breakdown. */
export function HealthTile({ health, meeting, onOpen }: { health: Health | null; meeting: Meeting | undefined; onOpen: () => void }) {
  if (!health || !meeting) {
    return (
      <div className="metric">
        <div className="k"><Icon name="checkCircle" size={14} />Meeting health</div>
        <div className="v faint">–</div>
        <div className="c">Add a meeting to score it</div>
      </div>
    );
  }
  return (
    <button className={`metric metric-btn ${healthTone(health.score)}`} onClick={onOpen} aria-label={`Meeting health ${health.score} of 100. Show how it is calculated`}>
      <div className="k"><Icon name="checkCircle" size={14} />Meeting health</div>
      <div className="v">{health.score}</div>
      <div className="c">{meeting.topic} · <span className="link-like">how is this scored?</span></div>
    </button>
  );
}

export function HealthBar({ h }: { h: Health }) {
  return (
    <div className="hbar" role="img" aria-label={h.parts.map((p) => `${p.label} ${p.points} of ${p.max}`).join(", ") + `, ${h.lost} lost`}>
      {h.parts.map((p) => <span key={p.key} style={{ width: `${p.points}%`, background: PART_COLOR[p.key] }} title={`${p.label}: ${p.points}`} />)}
      <span className="lost" style={{ width: `${h.lost}%` }} title={`Lost: ${h.lost}`} />
    </div>
  );
}

export function HealthSheet({ meetings, initial, onClose }: { meetings: Meeting[]; initial: string; onClose: () => void }) {
  const [id, setId] = useState(initial);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const m = meetings.find((x) => x.id === id) ?? meetings[meetings.length - 1];
  const h = m?.health;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="sheet" role="dialog" aria-modal="true" aria-labelledby="hs-title">
        <div className="sheet-head">
          <div style={{ flex: 1 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Meeting health</div>
            <h2 id="hs-title" style={{ fontSize: 16, marginTop: 2 }}>How the score is calculated</h2>
          </div>
          <button ref={closeRef} className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        </div>
        <div className="sheet-body">
          {meetings.length > 1 && (
            <select className="select" aria-label="Meeting" value={m.id} onChange={(e) => setId(e.target.value)}>
              {[...meetings].reverse().map((x) => <option key={x.id} value={x.id}>{x.topic} · {fmtDate(x.meeting_date)}</option>)}
            </select>
          )}
          {h && (
            <>
              <div className="row" style={{ alignItems: "baseline", gap: 10 }}>
                <span className={`hscore ${healthTone(h.score)}`}>{h.score}</span>
                <span className="muted small">out of 100 · {h.items} item{h.items === 1 ? "" : "s"} · {m.topic}</span>
              </div>
              <HealthBar h={h} />
              <div className="formula mono">H = 100 × (0.30 O + 0.25 D + 0.20 V + 0.15 (1 − A) + 0.10 (1 − C))</div>
              <table className="table">
                <thead><tr><th>Part</th><th>Measured</th><th style={{ textAlign: "right" }}>Points</th></tr></thead>
                <tbody>{h.parts.map((p) => (
                  <tr key={p.key}>
                    <td><span className="swatch" style={{ background: PART_COLOR[p.key] }} /><b className="mono">{p.key}</b> {p.label}
                      <div className="tiny muted">weight {p.weight.toFixed(2)}{p.key === "A" || p.key === "C" ? ", counts against" : ""}</div></td>
                    <td className="small">{p.detail}<div className="tiny muted">= {p.value.toFixed(2)}</div></td>
                    <td className="num" style={{ textAlign: "right" }}><b>{p.points}</b><span className="faint"> / {p.max}</span></td>
                  </tr>
                ))}</tbody>
              </table>
              <p className="small muted">Plain code on top of the checked items, never AI, so the same meeting always gets the same score.
                It goes up as you assign owners, confirm dates and resolve conflicts.</p>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

export type Preview = { origin: string; delays: Record<string, number>; absorbed: Record<string, number> } | null;

/** What-if slider: pick a task, drag its delay, see what turns red. All delays come precomputed from the server. */
export function WhatIfPanel({ actions, edges, version, onPreview }: {
  actions: Item[]; edges: { source: string; target: string }[]; version: number; onPreview: (p: Preview) => void;
}) {
  const sources = actions.filter((a) => edges.some((e) => e.source === a.id) && a.status !== "done");
  const [origin, setOrigin] = useState<string>("");
  const [days, setDays] = useState(0);
  const [data, setData] = useState<WhatIf | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const pick = origin && sources.some((s) => s.id === origin) ? origin : sources[0]?.id ?? "";

  useEffect(() => {
    if (!pick) { setData(null); return; }
    let live = true;
    api<WhatIf>(`whatif/${pick}`).then((w) => { if (live) { setData(w); setErr(null); } })
      .catch((e) => { if (live) setErr(e instanceof ApiError ? e.message : String(e)); });
    return () => { live = false; };
  }, [pick, version]);

  const step = data && data.origin === pick ? data.steps[days] : null;
  useEffect(() => {
    onPreview(step && days > 0 ? { origin: pick, delays: step.delays, absorbed: step.absorbed } : null);
  }, [step, days, pick, onPreview]);
  useEffect(() => () => onPreview(null), [onPreview]);

  if (!sources.length) return <div className="card-foot">What-if: no open task has anything waiting on it yet.</div>;
  const byId = new Map(actions.map((a) => [a.id, a]));
  const rows = step ? [...Object.keys(step.delays), ...Object.keys(step.absorbed)].filter((k) => k !== pick) : [];

  return (
    <div className="whatif">
      <div className="row" style={{ gap: 10 }}>
        <b className="small">What if</b>
        <select className="select" aria-label="Task that slips" value={pick} onChange={(e) => { setOrigin(e.target.value); }} style={{ width: 240 }}>
          {sources.map((s) => <option key={s.id} value={s.id}>{s.text}{s.owner ? ` (${s.owner})` : ""}</option>)}
        </select>
        <span className="small muted">slips by</span>
        <input type="range" min={0} max={10} step={1} value={days} onChange={(e) => setDays(Number(e.target.value))}
               aria-label="Days of delay" aria-valuetext={`${days} days`} style={{ flex: 1, minWidth: 140 }} />
        <b className="num" style={{ width: 52 }}>{days} day{days === 1 ? "" : "s"}</b>
      </div>
      {err && <div className="alert alert-error">{err}</div>}
      {step && (
        <div className={`whatif-out ${step.days_at_risk ? (step.teams_affected > 1 ? "is-red" : "is-amber") : ""}`} role="status" aria-live="polite">
          {days === 0 ? <span className="muted">Drag the slider to see how far a slip spreads. Each task&apos;s spare time (slack) absorbs part of it.</span> : (
            <>
              <div><b>{step.sentence}</b></div>
              {rows.length > 0 && (
                <table className="table" style={{ marginTop: 8 }}>
                  <thead><tr><th>Downstream task</th><th>Team</th><th>Slack</th><th style={{ textAlign: "right" }}>Effect</th></tr></thead>
                  <tbody>{rows.map((k) => {
                    const a = byId.get(k);
                    if (!a) return null;
                    const late = step.delays[k];
                    return (
                      <tr key={k}>
                        <td className="small">{a.text}</td>
                        <td className="small">{a.team ?? <span className="unknown">no owner</span>}</td>
                        <td><SlackEdit item={a} slack={data!.slack[k]} /></td>
                        <td className="num" style={{ textAlign: "right" }}>{late ? <b style={{ color: "var(--red)" }}>+{late} day{late === 1 ? "" : "s"}</b>
                          : <span style={{ color: "var(--green)" }}>absorbed{a.status === "done" ? " (done)" : ""}</span>}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SlackEdit({ item, slack }: { item: Item; slack: { days: number; source: string; why: string } | undefined }) {
  const [v, setV] = useState(String(slack?.days ?? 0));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setV(String(slack?.days ?? 0)); }, [slack?.days]);
  const save = async (days: number | null) => {
    setBusy(true);
    try { await api(`items/${item.id}/slack`, "PATCH", { days }); } finally { setBusy(false); }
  };
  return (
    <span className="row" style={{ gap: 6 }} title={slack?.why}>
      <input className="input" type="number" min={0} max={60} value={v} disabled={busy} aria-label={`Slack days for ${item.text}`}
             onChange={(e) => setV(e.target.value)} onBlur={() => { const n = Number(v); if (Number.isInteger(n) && n !== slack?.days) save(n); }}
             style={{ width: 58, height: 28 }} />
      <span className="tiny muted">{slack?.source === "manual"
        ? <>set by you · <button className="link" onClick={() => save(null)} disabled={busy}>reset</button></> : "from deadlines"}</span>
    </span>
  );
}

/** Clarify Loop: the drafted question for each flag, editable, sent to the suggested person. */
export function ClarifyDrafts({ item, people }: { item: Item; people: Person[] }) {
  const drafts = item.clarify ?? [];
  if (!drafts.length) return null;
  return (
    <div className="clarify">
      {drafts.map((d) => <Draft key={d.flag} item={item} d={d} people={people} />)}
    </div>
  );
}

function Draft({ item, d, people }: { item: Item; d: ClarifyDraft; people: Person[] }) {
  const [q, setQ] = useState(d.question);
  const [to, setTo] = useState(d.to[0]?.email ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const sent = (item.clarify_sent ?? []).filter((s) => s.flag === d.flag);
  const others = people.filter((p) => p.role === "employee" && !d.to.some((t) => t.email === p.email));
  const send = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ to: string; email_status: string | null }>(`items/${item.id}/clarify`, "POST", { flag: d.flag, to, question: q });
      setMsg({ ok: true, text: `Sent to ${r.to}${r.email_status === "sent" ? " by email and in the app" : " in the app"}.` });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally { setBusy(false); }
  };
  return (
    <div className="draft">
      <div className="tiny muted" style={{ fontWeight: 600 }}><Icon name="mail" size={12} /> Question to send{d.to.length ? ` · suggested: ${d.why}` : ""}</div>
      <textarea className="textarea" rows={2} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Question" />
      <div className="row">
        <select className="select" aria-label="Send to" value={to} onChange={(e) => setTo(e.target.value)} style={{ width: 190 }}>
          {!to && <option value="">Choose who to ask…</option>}
          {d.to.map((p) => <option key={p.email} value={p.email}>{p.name} ({p.team})</option>)}
          {others.length > 0 && <optgroup label="Someone else">{others.map((p) => <option key={p.email} value={p.email}>{p.name} ({p.team})</option>)}</optgroup>}
        </select>
        <button className="btn btn-sm" disabled={busy || !to || !q.trim()} onClick={send}><Icon name="mail" size={13} />Send question</button>
        {sent.length > 0 && <span className="tiny muted">Sent to {sent.map((s) => s.to).join(", ")}</span>}
      </div>
      {msg && <div className={`tiny ${msg.ok ? "" : "alert alert-error"}`} style={msg.ok ? { color: "var(--green)" } : undefined}>{msg.text}</div>}
    </div>
  );
}

export function ExportButtons() {
  return (
    <span className="row" style={{ gap: 6 }}>
      <a className="btn btn-sm" href="/api/backend/export.csv" download><Icon name="file" size={13} />CSV</a>
      <a className="btn btn-sm" href="/api/backend/export/jira.json" download><Icon name="file" size={13} />Jira JSON</a>
    </span>
  );
}
