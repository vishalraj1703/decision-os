"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, fmtDate, Item, ManagerState, STATUS_LABEL, VerifyInfo } from "@/lib/api";
import { statusLabel } from "./Flowchart";
import Icon from "./Icon";
import { TrustReceipt } from "./Trust";

type Person = { name: string; email: string; team: string; role: string };

export function Metrics({ stats, actions }: { stats: ManagerState["stats"]; actions: Item[] }) {
  const blocked = actions.filter((a) => a.status === "blocked" || a.overdue);
  const atRisk = actions.filter((a) => a.at_risk).length;
  return (
    <div className="card metrics">
      <div className="metric">
        <div className="k"><Icon name="users" size={14} />Teams in scope</div>
        <div className="v">{stats.teams_in_scope}</div>
        <div className="c">{actions.length} tracked task{actions.length === 1 ? "" : "s"}</div>
      </div>
      <div className={`metric${stats.blocked_handoffs ? " is-red" : ""}`}>
        <div className="k"><Icon name="ban" size={14} />Blocked handoffs</div>
        <div className="v">{stats.blocked_handoffs}</div>
        <div className="c">{blocked.length ? `${atRisk} downstream task${atRisk === 1 ? "" : "s"} at risk` : "Nothing is holding up another team"}</div>
      </div>
      <div className={`metric${stats.unassigned_actions ? " is-amber" : ""}`}>
        <div className="k"><Icon name="help" size={14} />Unassigned actions</div>
        <div className="v">{stats.unassigned_actions}</div>
        <div className="c">{stats.unassigned_actions ? "Owner or date not stated in the notes" : "Every task has an owner and a date"}</div>
      </div>
    </div>
  );
}

export function Callout({ c }: { c: ManagerState["callout"] }) {
  const icon = c.severity === "red" ? "octagon" : c.severity === "amber" ? "alert" : "info";
  return (
    <div className={`callout ${c.severity}`} role="status" aria-live="polite">
      <div className="bar" />
      <div className="inner">
        <Icon name={icon} size={20} />
        <div>
          <div className="msg">{c.text}</div>
          <div className="src">{c.source === "ai" ? "Diagnosis by the Qualcomm model" : "Summary from task status. The model's diagnosis appears when live inference is configured."}</div>
        </div>
      </div>
    </div>
  );
}

function Unknown({ children }: { children: React.ReactNode }) {
  return <span className="unknown">{children}<Icon name="help" size={13} /></span>;
}

function short(q: string, n = 12) {
  const w = q.split(/\s+/);
  return w.length > n ? w.slice(0, n).join(" ") + "…" : q;
}

function Deadline({ i }: { i: Item }) {
  if (i.deadline_date) {
    return <span>{fmtDate(i.deadline_date)}{i.deadline_status === "needs_confirmation" && <div className="tiny" style={{ color: "var(--amber)" }}>“{i.deadline_raw}” · confirm date</div>}</span>;
  }
  if (i.deadline_status === "after_dependency") return <span className="muted">After dependency</span>;
  return <Unknown>unclear — needs follow-up</Unknown>;
}

type Filter = "all" | "review" | "risk" | "done";

export function ActionTable({ actions, onSource }: { actions: Item[]; onSource: (i: Item) => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const rows = actions.filter((a) =>
    filter === "all" ? true : filter === "review" ? a.missing_info.length > 0
      : filter === "risk" ? a.at_risk || a.overdue || a.status === "blocked" : a.status === "done");
  const count = (f: Filter) => actions.filter((a) => f === "review" ? a.missing_info.length > 0 : f === "risk" ? a.at_risk || a.overdue || a.status === "blocked" : a.status === "done").length;
  return (
    <div className="card" id="actions">
      <div className="card-head">
        <h2>Action items</h2>
        <span className="sub num">{actions.length}</span>
        <div className="spacer" />
        <div className="segmented" role="group" aria-label="Filter actions">
          {([["all", "All"], ["review", "Needs review"], ["risk", "At risk"], ["done", "Done"]] as [Filter, string][]).map(([f, l]) => (
            <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>{l}{f !== "all" && <span className="num" style={{ marginLeft: 5, color: "var(--faint)" }}>{count(f)}</span>}</button>
          ))}
        </div>
      </div>
      {rows.length === 0 ? <div className="empty">{actions.length ? "Nothing in this view." : "No action items yet."}</div> : (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th style={{ width: "26%" }}>Task</th><th>Owner</th><th>Deadline</th><th>Status</th><th style={{ width: "30%" }}>Evidence</th><th>Trust receipt</th></tr></thead>
            <tbody>
              {rows.map((a) => {
                const missing = a.missing_info.length > 0;
                return (
                  <tr key={a.id} id={`row-${a.id}`} className={missing ? "is-missing" : ""}>
                    <td>
                      <div className="task-title">{a.text}</div>
                      <div className="tiny muted" style={{ marginTop: 2 }}>{a.meeting.topic} · {fmtDate(a.meeting.date)}</div>
                      {missing && <span className="tag tag-review" style={{ marginTop: 6 }}>Needs review</span>}
                    </td>
                    <td>{a.owner ? <><div>{a.owner}</div><div className="tiny muted">{a.team}</div></> : <Unknown>UNKNOWN</Unknown>}</td>
                    <td><Deadline i={a} /></td>
                    <td><span className={`status s-${a.color}`}><i />{statusLabel(a)}</span>
                      {a.status === "blocked" && a.blocked_reason && <div className="tiny muted" style={{ marginTop: 3 }}>{a.blocked_reason}</div>}</td>
                    <td><span className="quote">{short(a.evidence_quote)}</span><div><button className="link" onClick={() => onSource(a)} aria-label={`View source for ${a.text}`}>View source</button></div></td>
                    <td><TrustReceipt i={a} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="card-foot">Trust receipt: the quote was found in the notes, the Verifier confirmed its meaning, and the model&apos;s self-reported confidence (not a measured accuracy). Every row links to the sentence it came from.</div>
    </div>
  );
}

const MISSING: Record<string, string> = { owner: "Owner not stated", deadline: "Deadline not stated", deadline_confirmation: "Date needs confirmation" };

export function NeedsReview({ items, people, onSource }: { items: Item[]; people: Person[]; onSource: (i: Item) => void }) {
  return (
    <div className="card" id="review">
      <div className="card-head">
        <h2>Needs review</h2><span className="sub num">{items.length}</span>
        <div className="spacer" />
        <span className="tiny muted">Gaps the notes leave open</span>
      </div>
      {items.length === 0 ? <div className="empty">Nothing to review. Every task has an owner and a date from the notes.</div> : (
        <div className="list">{items.map((i) => <ReviewItem key={i.id} item={i} people={people} onSource={onSource} />)}</div>
      )}
    </div>
  );
}

function ReviewItem({ item, people, onSource }: { item: Item; people: Person[]; onSource: (i: Item) => void }) {
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
  const needsOwner = item.missing_info.includes("owner");
  const needsDate = item.missing_info.includes("deadline");
  const confirm = item.missing_info.includes("deadline_confirmation");
  return (
    <div className="list-item">
      <div className="row between">
        <div>
          <div className="tiny muted" style={{ fontWeight: 600 }}>{item.kind === "risk" ? "Risk" : "Task"}{item.owner ? ` · ${item.owner}` : ""}</div>
          <div className="task-title">{item.text}</div>
        </div>
        {item.review_state === "follow_up" && <span className="tag tag-accent">Follow-up meeting</span>}
      </div>
      <div className="missing">{item.missing_info.map((m) => <span key={m} className="tag tag-review">{MISSING[m] ?? m}</span>)}</div>
      <div className="small"><span className="quote">{item.evidence_quote}</span> <button className="link" onClick={() => onSource(item)}>View source</button></div>
      {item.checks.filter((c) => c.includes("not named")).map((c) => (
        <div key={c} className="why"><Icon name="info" size={13} />{c}</div>
      ))}
      <div className="row">
        {needsOwner && (
          <>
            <select className="select" aria-label="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} style={{ width: 168 }}>
              <option value="">Choose owner…</option>
              {people.filter((p) => p.role === "employee").map((p) => <option key={p.email} value={p.email}>{p.name} ({p.team})</option>)}
            </select>
            <button className="btn btn-primary" disabled={busy || !owner} onClick={() => act("assign_owner", owner)}>Assign</button>
          </>
        )}
        {confirm && <button className="btn btn-primary" disabled={busy} onClick={() => act("confirm_deadline")}><Icon name="check" size={14} />Confirm {fmtDate(item.deadline_date)}</button>}
        {(needsDate || confirm) && (
          <>
            <input className="input" type="date" aria-label="Deadline" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 150 }} />
            <button className="btn" disabled={busy || !date} onClick={() => act("set_deadline", date)}>Set date</button>
          </>
        )}
        <div className="spacer" />
        {item.review_state !== "follow_up" && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act("follow_up")}>Follow-up meeting</button>}
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act("discard")}>Discard</button>
      </div>
      {err && <div className="alert alert-error">{err}</div>}
    </div>
  );
}

export function TeamStatus({ teams }: { teams: ManagerState["teams"] }) {
  if (!teams.length) return null;
  const label: Record<string, string> = { red: "Blocked", orange: "Needs attention", grey: "Waiting", green: "Healthy" };
  return (
    <div className="card">
      <div className="teams">
        {teams.map((t) => (
          <div key={t.team} className="team">
            <b>{t.team}</b>
            <span className={`status s-${t.color}`}><i />{label[t.color]}</span>
            <span className="tiny muted">{t.tasks} task{t.tasks === 1 ? "" : "s"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function NewMeeting({ demos, model, live, onClose }: {
  demos: { label: string; date: string; notes: string }[]; model: string; live: boolean; onClose: () => void;
}) {
  const t = new Date();
  const iso = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(iso);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose, busy]);

  async function run() {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ items: number; attempts: number; latency_ms: number; topic: string; rejected: { text: string; by?: string }[];
        verify: VerifyInfo; redactions: Record<string, number> }>("extract", "POST", { notes, meeting_date: date });
      const parts = [`${r.items} item${r.items === 1 ? "" : "s"} extracted from “${r.topic}”`];
      if (live) parts.push(`in ${(r.latency_ms / 1000).toFixed(1)} s`);
      if (r.attempts > 1) parts.push("after one corrective retry");
      let text = parts.join(" ") + ".";
      const masked = Object.values(r.redactions ?? {}).reduce((a, b) => a + b, 0);
      if (masked) text += ` Masked ${masked} contact detail${masked === 1 ? "" : "s"} (email, phone or ID) before the AI saw the notes.`;
      const noQuote = r.rejected.filter((x) => x.by !== "verifier").length;
      if (noQuote) text += ` ${noQuote} claim${noQuote === 1 ? " was" : "s were"} rejected because no matching sentence exists in the notes.`;
      if (r.verify?.status === "ok") {
        const v = r.verify;
        const did = [v.removed && `removed ${v.removed}`, v.corrected && `corrected ${v.corrected}`].filter(Boolean).join(" and ");
        text += ` The Verifier ${did || "confirmed every item"}${live && v.latency_ms ? ` in ${(v.latency_ms / 1000).toFixed(1)} s` : ""}.`;
      } else if (r.verify?.status === "failed") {
        text += " The Verifier did not answer, so items are marked not verified.";
      }
      setMsg({ ok: true, text });
      setNotes("");
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="scrim" onClick={() => !busy && onClose()} />
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="nm-title">
        <div className="card-head" style={{ borderBottom: "1px solid var(--line)" }}>
          <h2 id="nm-title" style={{ fontSize: 16 }}>Add meeting notes</h2>
          <div className="spacer" />
          <button className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose} disabled={busy}><Icon name="x" /></button>
        </div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {demos.length > 0 && (
            <div className="row small"><span className="muted">Examples:</span>
              {demos.map((d) => <button key={d.label} className="btn btn-sm" onClick={() => { setNotes(d.notes); setDate(d.date); }} disabled={busy}>{d.label}</button>)}
            </div>
          )}
          <div>
            <label className="label" htmlFor="nm-notes">Notes</label>
            <textarea id="nm-notes" ref={ref} className="textarea" rows={8} value={notes} onChange={(e) => setNotes(e.target.value)}
                      placeholder="Paste a transcript, bullet points or a rough summary." />
          </div>
          <div className="row">
            <div style={{ width: 170 }}>
              <label className="label" htmlFor="nm-date">Meeting date</label>
              <input id="nm-date" className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <p className="small muted" style={{ flex: 1, alignSelf: "flex-end", minWidth: 200 }}>Relative dates like “Friday” are read from this date and flagged for confirmation.</p>
          </div>
          {msg && <div className={`alert ${msg.ok ? "alert-ok" : "alert-error"}`} role="status"><Icon name={msg.ok ? "checkCircle" : "alert"} size={15} />{msg.text}</div>}
        </div>
        <div className="card-foot row between" style={{ background: "var(--surface-2)" }}>
          <span>Sent to {live ? `Qualcomm Cloud AI (${model})` : "the replay engine (no Qualcomm key)"}</span>
          <div className="row">
            <button className="btn" onClick={onClose} disabled={busy}>{msg?.ok ? "Done" : "Cancel"}</button>
            <button className="btn btn-primary" onClick={run} disabled={busy || !notes.trim()}>
              {busy ? <><span className="spinner" />Asking the model…</> : "Extract"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export { STATUS_LABEL };
