"use client";

import { useCallback, useState } from "react";
import { api, ApiError, EmployeeState, fmtDate, Item, Status, STATUS_LABEL, useLiveState } from "@/lib/api";
import { Bell, EvidenceDrawer, TopBar } from "./Shell";

const STATUSES: Status[] = ["not_started", "in_progress", "blocked", "done"];

export default function EmployeeDashboard() {
  const { state, error } = useLiveState<EmployeeState>();
  const [evidence, setEvidence] = useState<Item | null>(null);
  const [blockOpen, setBlockOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const setStatus = useCallback(async (id: string, status: Status, reason?: string) => {
    setErr(null);
    try { await api(`items/${id}/status`, "PATCH", { status, reason }); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
  }, []);

  if (!state) return <div className="page">{error ? <div className="alert alert-error">{error}</div> : <p className="muted">Loading…</p>}</div>;
  const s = state;
  const open = s.tasks.filter((t) => t.status !== "done");

  return (
    <>
      <TopBar ai={s.ai} me={s.me} today={s.today} simulated={s.simulated}
              bell={<Bell items={s.notifications} unread={s.unread} onRead={() => api("notifications/read", "POST", {})} />} />
      <main className="page">
        {(error || err) && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error || err}</div>}
        <div className="grid-main">
          <div className="stack">
            <div className="stat" style={{ maxWidth: 260 }}><b>{open.length}</b><span>Your tasks</span></div>
            {s.tasks.length === 0 && <div className="card muted">No tasks are assigned to you in any meeting.</div>}
            {s.tasks.map((t) => <TaskCard key={t.id} t={t} onStatus={setStatus} onEvidence={setEvidence} />)}
            {open.length > 0 && (
              <button className="btn-gold" style={{ width: "100%", justifyContent: "center", padding: "14px", fontSize: 16, background: "var(--red)", borderColor: "var(--red)", color: "#fff" }}
                      onClick={() => setBlockOpen(true)}>Mark Blocked</button>
            )}
          </div>
          <aside className="card" aria-labelledby="dep-h">
            <h2 id="dep-h">Dependency updates</h2>
            <p className="faint" style={{ fontSize: 12.5 }}>What your work is waiting on, and when you can start.</p>
            {s.notifications.length === 0 && <p className="muted">No updates yet.</p>}
            {s.notifications.map((n) => (
              <div key={n.id} className={`bell-item${n.read ? "" : " unread"}`} style={{ borderRadius: 8, marginBottom: 6 }}>
                <div>{n.text}</div>
                <div className="faint" style={{ fontSize: 11.5 }}>{new Date(n.created_at).toLocaleString()}</div>
              </div>
            ))}
          </aside>
        </div>
      </main>
      {blockOpen && <BlockModal tasks={open} onClose={() => setBlockOpen(false)} onSubmit={async (id, reason) => { await setStatus(id, "blocked", reason); setBlockOpen(false); }} />}
      {evidence && <EvidenceDrawer meetingId={evidence.meeting_id} start={evidence.ev_start} end={evidence.ev_end} title={evidence.text} onClose={() => setEvidence(null)} />}
    </>
  );
}

function TaskCard({ t, onStatus, onEvidence }: { t: Item; onStatus: (id: string, s: Status) => void; onEvidence: (i: Item) => void }) {
  const flag = t.status === "done" ? "chip-green" : t.status === "blocked" || t.overdue ? "chip-red" : t.at_risk ? "chip-orange" : "chip-grey";
  const flagText = t.status === "done" ? "Done" : t.status === "blocked" ? "Blocked" : t.overdue ? "Overdue" : t.at_risk ? "Waiting on a blocked task" : "On track";
  return (
    <section id={t.id} className="card" style={{ borderLeft: `4px solid var(--${t.color})` }} aria-label={t.text}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>{t.text}</h2>
        <span className={`chip ${flag}`}>{flagText}</span>
      </div>
      <p className="faint" style={{ fontSize: 12.5, margin: "4px 0 10px" }}>From “{t.meeting.topic}” · meeting of {fmtDate(t.meeting.date)}</p>
      <div className="row" style={{ gap: 18, alignItems: "flex-start" }}>
        <div><label>Deadline</label>{t.deadline_date ? t.deadline_text : t.deadline_status === "after_dependency" ? "after its dependency" : <span className="unknown">unclear</span>}</div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label>Waiting on</label>
          {t.blocked_by && t.blocked_by.length ? t.blocked_by.map((b) => (
            <div key={b.id}>{b.owner ?? "UNKNOWN"}: {b.text} <span className={`chip ${b.status === "done" ? "chip-green" : b.status === "blocked" || b.overdue ? "chip-red" : "chip-grey"}`}>{b.overdue && b.status !== "done" ? "Overdue" : STATUS_LABEL[b.status]}</span></div>
          )) : <span className="muted">Nothing</span>}
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label>Blocking</label>
          {t.blocking && t.blocking.length ? t.blocking.map((b) => <div key={b.id}>{b.owner ?? "UNKNOWN"}: {b.text}</div>) : <span className="muted">Nobody</span>}
        </div>
      </div>
      <p className="evidence" style={{ fontSize: 13, margin: "10px 0" }}>“{t.evidence_quote}” <button className="btn-link" onClick={() => onEvidence(t)}>view source</button></p>
      <div className="row">
        <label htmlFor={`st-${t.id}`} style={{ margin: 0 }}>Status</label>
        <select id={`st-${t.id}`} value={t.status} onChange={(e) => onStatus(t.id, e.target.value as Status)} style={{ width: 170 }}>
          {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
        {t.status === "blocked" && t.blocked_reason && <span className="muted">Reason: {t.blocked_reason}</span>}
      </div>
    </section>
  );
}

function BlockModal({ tasks, onClose, onSubmit }: { tasks: Item[]; onClose: () => void; onSubmit: (id: string, reason: string) => Promise<void> }) {
  const [id, setId] = useState(tasks[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-labelledby="blk-h" className="card"
           style={{ position: "fixed", top: "20%", left: "50%", transform: "translateX(-50%)", width: "min(460px, 92vw)", zIndex: 42 }}>
        <h2 id="blk-h">Mark a task blocked</h2>
        <p className="muted">Your manager is notified and the flowchart turns this task red.</p>
        <div className="stack">
          <div>
            <label htmlFor="blk-task">Which task?</label>
            <select id="blk-task" value={id} onChange={(e) => setId(e.target.value)}>
              {tasks.map((t) => <option key={t.id} value={t.id}>{t.text}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="blk-why">Reason (optional)</label>
            <input id="blk-why" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Waiting on the API contract" autoFocus />
          </div>
          <div className="row">
            <button className="btn-gold" disabled={!id || busy} onClick={async () => { setBusy(true); await onSubmit(id, reason); setBusy(false); }}>Mark blocked</button>
            <button onClick={onClose}>Cancel</button>
          </div>
        </div>
      </div>
    </>
  );
}
