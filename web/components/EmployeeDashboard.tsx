"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, EmployeeState, fmtDate, Item, Status, STATUS_LABEL, useLiveState } from "@/lib/api";
import { statusLabel } from "./Flowchart";
import Icon from "./Icon";
import { Bell, EnginePill, NavLink, SimPill, Sidebar, SourceSheet, UserMenu } from "./Shell";

const STATUSES: Status[] = ["not_started", "in_progress", "blocked", "done"];

export default function EmployeeDashboard() {
  const { state, error } = useLiveState<EmployeeState>();
  const [source, setSource] = useState<Item | null>(null);
  const [blocking, setBlocking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const setStatus = useCallback(async (id: string, status: Status, reason?: string) => {
    setErr(null);
    try { await api(`items/${id}/status`, "PATCH", { status, reason }); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
  }, []);

  if (!state) return <div className="content">{error ? <div className="alert alert-error">{error}</div> : <div className="row muted"><span className="spinner dark" />Loading…</div>}</div>;
  const s = state;
  const open = s.tasks.filter((t) => t.status !== "done");
  const done = s.tasks.filter((t) => t.status === "done");
  const waiting = open.filter((t) => t.blocked_by?.some((b) => b.status !== "done")).length;

  return (
    <div className="shell">
      <Sidebar ai={s.ai}>
        <nav className="nav" aria-label="Sections">
          <div className="nav-title">My work</div>
          <NavLink href="#tasks" icon="list" label="My tasks" count={open.length} />
          <NavLink href="#updates" icon="bell" label="Updates" count={s.unread} alert />
        </nav>
      </Sidebar>
      <div className="main">
        <header className="topbar">
          <div className="title">
            <h1 style={{ fontSize: 16 }}>My tasks</h1>
            <span>{open.length} open{waiting ? ` · ${waiting} waiting on someone` : ""}{done.length ? ` · ${done.length} done` : ""}</span>
          </div>
          <div className="spacer" />
          <SimPill today={s.today} simulated={s.simulated} />
          <EnginePill ai={s.ai} />
          {open.length > 0 && <button className="btn btn-danger" onClick={() => setBlocking(true)}><Icon name="ban" size={15} />Mark blocked</button>}
          <Bell items={s.notifications} unread={s.unread} />
          <UserMenu me={s.me} />
        </header>
        <main className="content">
          {(error || err) && <div className="alert alert-error"><Icon name="alert" size={15} />{error || err}</div>}
          <div className="grid-2">
            <div className="col" id="tasks">
              {s.tasks.length === 0 && <div className="card empty">No tasks are assigned to you in any meeting.</div>}
              {[...open, ...done].map((t) => <TaskCard key={t.id} t={t} onStatus={setStatus} onSource={setSource} />)}
            </div>
            <div className="card" id="updates">
              <div className="card-head"><h2>Dependency updates</h2><div className="spacer" /><span className="tiny muted">What you're waiting on</span></div>
              {s.notifications.length === 0 ? <div className="empty">No updates yet. You'll see here when work you depend on is done or stuck.</div> : (
                <div>{s.notifications.map((n) => (
                  <div key={n.id} className={`note-item${n.read ? "" : " unread"}`}>
                    <span className="d" />
                    <div>{n.text}<time dateTime={n.created_at}>{new Date(n.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time></div>
                  </div>
                ))}</div>
              )}
            </div>
          </div>
        </main>
      </div>
      {blocking && <BlockDialog tasks={open} onClose={() => setBlocking(false)} onSubmit={async (id, why) => { await setStatus(id, "blocked", why); setBlocking(false); }} />}
      {source && <SourceSheet meetingId={source.meeting_id} start={source.ev_start} end={source.ev_end} title={source.text}
                              subtitle={`From ${source.meeting.topic}, ${fmtDate(source.meeting.date)}`} onClose={() => setSource(null)} />}
    </div>
  );
}

function Dep({ b }: { b: NonNullable<Item["blocked_by"]>[number] }) {
  const cls = b.status === "done" ? "s-green" : b.status === "blocked" || b.overdue ? "s-red" : "s-grey";
  return (
    <div className="row" style={{ gap: 6 }}>
      <span className={`status ${cls}`}><i /></span>
      <span><b style={{ fontWeight: 550 }}>{b.owner ?? "Unassigned"}</b> · {b.text}</span>
      <span className="tiny muted">{b.overdue && b.status !== "done" ? "overdue" : STATUS_LABEL[b.status].toLowerCase()}</span>
    </div>
  );
}

function TaskCard({ t, onStatus, onSource }: { t: Item; onStatus: (id: string, s: Status) => void; onSource: (i: Item) => void }) {
  return (
    <section id={t.id} className="card" aria-label={t.text} style={{ boxShadow: `inset 3px 0 0 var(--${t.color === "orange" ? "amber" : t.color === "grey" ? "line-strong" : t.color})` }}>
      <div className="task-card">
        <div className="row between" style={{ alignItems: "flex-start" }}>
          <div>
            <h2 style={{ fontSize: 15.5 }}>{t.text}</h2>
            <div className="tiny muted" style={{ marginTop: 3 }}>From {t.meeting.topic} · {fmtDate(t.meeting.date)}</div>
          </div>
          <span className={`status s-${t.color}`}><i />{statusLabel(t)}</span>
        </div>
        <div className="facts">
          <div>
            <div className="label">Deadline</div>
            {t.deadline_date ? <>{fmtDate(t.deadline_date)}{t.deadline_status === "needs_confirmation" && <div className="tiny" style={{ color: "var(--amber)" }}>“{t.deadline_raw}” · to be confirmed</div>}</>
              : t.deadline_status === "after_dependency" ? <span className="muted">When your dependency is done</span> : <span className="unknown">Not set</span>}
          </div>
          <div>
            <div className="label">Waiting on</div>
            {t.blocked_by?.length ? t.blocked_by.map((b) => <Dep key={b.id} b={b} />) : <span className="muted">Nothing</span>}
          </div>
          <div>
            <div className="label">Unblocks</div>
            {t.blocking?.length ? t.blocking.map((b) => <div key={b.id}><b style={{ fontWeight: 550 }}>{b.owner ?? "Unassigned"}</b> · {b.text}</div>) : <span className="muted">No one</span>}
          </div>
        </div>
        <div className="small"><span className="quote">{t.evidence_quote}</span> <button className="link" onClick={() => onSource(t)}>View source</button></div>
        <div className="row" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <label className="label" htmlFor={`st-${t.id}`} style={{ margin: 0 }}>Status</label>
          <select id={`st-${t.id}`} className="select" value={t.status} onChange={(e) => onStatus(t.id, e.target.value as Status)} style={{ width: 160 }}>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
          {t.status === "blocked" && t.blocked_reason && <span className="small muted">Reason: {t.blocked_reason}</span>}
        </div>
      </div>
    </section>
  );
}

function BlockDialog({ tasks, onClose, onSubmit }: { tasks: Item[]; onClose: () => void; onSubmit: (id: string, reason: string) => Promise<void> }) {
  const [id, setId] = useState(tasks[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="blk-title" style={{ width: "min(460px, 94vw)" }}>
        <div className="card-head"><h2 id="blk-title" style={{ fontSize: 16 }}>Mark a task as blocked</h2><div className="spacer" />
          <button className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}><Icon name="x" /></button></div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <p className="small muted">Your manager is notified right away and the task turns red on the team graph.</p>
          <div>
            <label className="label" htmlFor="blk-task">Task</label>
            <select id="blk-task" className="select" value={id} onChange={(e) => setId(e.target.value)}>
              {tasks.map((t) => <option key={t.id} value={t.id}>{t.text}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="blk-why">What's in the way? <span className="faint">(optional)</span></label>
            <input id="blk-why" ref={ref} className="input" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="Waiting on the API contract" />
          </div>
        </div>
        <div className="card-foot row" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-danger" disabled={!id || busy} onClick={async () => { setBusy(true); await onSubmit(id, reason); setBusy(false); }}>Mark blocked</button>
        </div>
      </div>
    </>
  );
}
