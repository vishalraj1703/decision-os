"use client";

import { useState } from "react";
import { api, ApiError, Item, ManagerState, STATUS_LABEL } from "@/lib/api";

export function StatsBar({ stats }: { stats: ManagerState["stats"] }) {
  return (
    <div className="stats">
      <div className="stat"><b>{stats.teams_in_scope}</b><span>Teams in scope</span></div>
      <div className={`stat${stats.blocked_handoffs ? " alarm" : ""}`}><b>{stats.blocked_handoffs}</b><span>Blocked handoffs</span></div>
      <div className={`stat${stats.unassigned_actions ? " warn" : ""}`}><b>{stats.unassigned_actions}</b><span>Unassigned actions</span></div>
    </div>
  );
}

export function Callout({ c }: { c: ManagerState["callout"] }) {
  return (
    <div className={`callout callout-${c.severity}`} role="status" aria-live="polite">
      <span aria-hidden="true" style={{ fontSize: 24 }}>{c.severity === "red" ? "⛔" : c.severity === "amber" ? "⚠" : "ℹ"}</span>
      <div>
        {c.text}
        <small>{c.source === "ai" ? "Diagnosis by the Qualcomm model" : "Rule-based summary (AI diagnosis pending or unavailable)"}</small>
      </div>
    </div>
  );
}

function Unknown({ label }: { label: string }) {
  return <span className="unknown">{label}<i className="qmark" aria-hidden="true">?</i></span>;
}

function Confidence({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  const cls = v >= 0.85 ? "conf-high" : v >= 0.6 ? "conf-mid" : "conf-low";
  return <span className={cls} title="Self-reported by the model, not calibrated">{pct}%</span>;
}

function short(q: string) {
  const w = q.split(/\s+/);
  return w.length > 11 ? w.slice(0, 11).join(" ") + "…" : q;
}

export function ActionTable({ actions, onEvidence }: { actions: Item[]; onEvidence: (i: Item) => void }) {
  if (!actions.length) return <p className="muted">No action items yet.</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th>Task</th><th>Owner</th><th>Deadline</th><th>Status</th><th>Evidence</th><th>Confidence*</th></tr></thead>
        <tbody>
          {actions.map((a) => {
            const missing = a.missing_info.length > 0;
            return (
              <tr key={a.id} className={missing ? "missing" : ""} id={`row-${a.id}`}>
                <td>
                  {a.text}
                  {missing && <> <span className="chip chip-review">Needs Review</span></>}
                  <div className="faint" style={{ fontSize: 11.5 }}>{a.meeting.topic} · {a.meeting.date}</div>
                </td>
                <td>{a.owner ?? <Unknown label="UNKNOWN" />}{a.team && <div className="faint" style={{ fontSize: 11.5 }}>{a.team}</div>}</td>
                <td>{a.deadline_date ? a.deadline_text : a.deadline_status === "after_dependency" ? <span className="muted">after dependency</span> : <Unknown label="unclear — needs follow-up" />}</td>
                <td><span className={`chip chip-${a.color}`}>{a.overdue && a.status !== "done" ? "Overdue" : a.at_risk ? "At risk" : STATUS_LABEL[a.status]}</span></td>
                <td><span className="evidence">“{short(a.evidence_quote)}”</span> <button className="btn-link" onClick={() => onEvidence(a)} aria-label={`View source for ${a.text}`}>view source</button></td>
                <td><Confidence v={a.confidence} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="faint" style={{ fontSize: 11.5, marginTop: 6 }}>* Confidence is self-reported by the model, not a measured accuracy. Trust comes from the evidence link.</p>
    </div>
  );
}

const MISSING_LABEL: Record<string, string> = {
  owner: "Owner not stated in notes", deadline: "Deadline not stated in notes", deadline_confirmation: "Deadline wording is relative; confirm the date",
};

export function NeedsReview({ items, people, onEvidence }: {
  items: Item[]; people: { name: string; email: string; team: string; role: string }[]; onEvidence: (i: Item) => void;
}) {
  if (!items.length) return <p className="muted">Nothing needs review. Every item has an owner and a deadline from the notes.</p>;
  return (
    <div className="stack">
      {items.map((i) => <ReviewCard key={i.id} item={i} people={people} onEvidence={onEvidence} />)}
    </div>
  );
}

function ReviewCard({ item, people, onEvidence }: { item: Item; people: { name: string; email: string; team: string; role: string }[]; onEvidence: (i: Item) => void }) {
  const [owner, setOwner] = useState("");
  const [date, setDate] = useState(item.deadline_date ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (action: string, value?: string) => {
    setBusy(true); setErr(null);
    try { await api(`items/${item.id}/resolve`, "POST", { action, value }); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  return (
    <div className="card" style={{ background: "var(--panel-2)" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>{item.kind === "action" ? "Task" : item.kind === "risk" ? "Risk" : "Decision"}: {item.text}</strong>
        {item.review_state === "follow_up" && <span className="chip chip-gold">Follow-up meeting</span>}
      </div>
      <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
        {item.missing_info.map((m) => <li key={m} className="muted">{MISSING_LABEL[m] ?? m}{m === "deadline_confirmation" && item.deadline_date ? `: '${item.deadline_raw}' read as ${item.deadline_text.replace(" (needs confirmation)", "")}` : ""}</li>)}
      </ul>
      {item.checks.length > 0 && <p className="faint" style={{ fontSize: 12 }}>{item.checks.join(" ")}</p>}
      <p className="evidence" style={{ fontSize: 13 }}>“{item.evidence_quote}” <button className="btn-link" onClick={() => onEvidence(item)}>view source</button></p>
      <div className="row">
        {item.missing_info.includes("owner") && item.kind !== "decision" && (
          <>
            <select aria-label="Assign owner" value={owner} onChange={(e) => setOwner(e.target.value)} style={{ width: 170 }}>
              <option value="">Assign owner…</option>
              {people.filter((p) => p.role === "employee").map((p) => <option key={p.email} value={p.email}>{p.name} · {p.team}</option>)}
            </select>
            <button disabled={busy || !owner} onClick={() => act("assign_owner", owner)}>Assign</button>
          </>
        )}
        {item.missing_info.includes("deadline_confirmation") && (
          <button disabled={busy} onClick={() => act("confirm_deadline")}>Confirm {item.deadline_text.replace(" (needs confirmation)", "")}</button>
        )}
        {(item.missing_info.includes("deadline") || item.missing_info.includes("deadline_confirmation")) && (
          <>
            <input type="date" aria-label="Set deadline" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 150 }} />
            <button disabled={busy || !date} onClick={() => act("set_deadline", date)}>Set deadline</button>
          </>
        )}
        {item.review_state !== "follow_up" && <button disabled={busy} onClick={() => act("follow_up")}>Needs follow-up meeting</button>}
        <button disabled={busy} onClick={() => act("discard")} className="btn-small">Discard as noise</button>
      </div>
      {err && <div className="alert alert-error" style={{ marginTop: 8 }}>{err}</div>}
    </div>
  );
}

export function TeamStrip({ teams }: { teams: ManagerState["teams"] }) {
  if (!teams.length) return null;
  return (
    <div className="strip" aria-label="Team status">
      {teams.map((t) => (
        <div key={t.team} className="team-pill">
          <i className={`dot dot-${t.color}`} aria-hidden="true" />
          <div><strong>{t.team}</strong><div className="faint" style={{ fontSize: 12 }}>{t.label} · {t.tasks} task{t.tasks === 1 ? "" : "s"}</div></div>
        </div>
      ))}
    </div>
  );
}

export function ExtractBox({ model, live, demos }: { model: string; live: boolean; demos: { label: string; date: string; notes: string }[] }) {
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(iso);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function extract() {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ items: number; attempts: number; latency_ms: number; topic: string; rejected: { text: string; reason: string }[] }>(
        "extract", "POST", { notes, meeting_date: date });
      const rej = r.rejected.length ? ` ${r.rejected.length} claim${r.rejected.length === 1 ? "" : "s"} rejected (no matching sentence).` : "";
      setMsg({ ok: true, text: `“${r.topic}”: ${r.items} items extracted${live ? ` in ${(r.latency_ms / 1000).toFixed(1)} s` : ""}${r.attempts > 1 ? " after one corrective retry" : ""}.${rej}` });
      setNotes("");
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Meeting notes</h2>
        <div className="row">
          {demos.map((d) => <button key={d.label} className="btn-small" onClick={() => { setNotes(d.notes); setDate(d.date); }} disabled={busy}>Load {d.label}</button>)}
        </div>
      </div>
      <textarea aria-label="Meeting notes" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} style={{ marginTop: 10 }}
                placeholder="Paste raw meeting notes: transcript, bullet list or summary." />
      <div className="row" style={{ marginTop: 10 }}>
        <label htmlFor="mdate" style={{ margin: 0 }}>Meeting date</label>
        <input id="mdate" type="date" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 160 }} />
        <button className="btn-gold" onClick={extract} disabled={busy || !notes.trim()}>{busy ? <><span className="spinner" /> Asking the model...</> : "Extract"}</button>
        {busy && <span className="faint">{model}</span>}
      </div>
      {msg && <div className={`alert ${msg.ok ? "alert-ok" : "alert-error"}`} style={{ marginTop: 10 }} role="status">{msg.text}</div>}
      <p className="faint" style={{ fontSize: 12, marginTop: 8 }}>Notes are sent to Qualcomm Cloud AI for extraction. Every item must quote a sentence from them.</p>
    </div>
  );
}
