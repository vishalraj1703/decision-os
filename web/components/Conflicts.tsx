"use client";

import { useState } from "react";
import { api, ApiError, Conflict, fmtDate, Meeting } from "@/lib/api";
import Icon from "./Icon";

const RESOLVED: Record<Conflict["status"], string> = {
  open: "Open", confirmed_current: "New decision confirmed", reverted: "Reverted", follow_up: "Follow-up meeting",
};

export default function Conflicts({ items, meetings, live }: { items: Conflict[]; meetings: Meeting[]; live: boolean }) {
  const open = items.filter((c) => c.status === "open").length;
  const date = (id: string | null) => fmtDate(meetings.find((m) => m.id === id)?.meeting_date ?? null);
  return (
    <div className="card" id="conflicts">
      <div className="card-head">
        <h2>Decision conflicts</h2>
        {open > 0 && <span className="tag tag-red">{open} open</span>}
        <div className="spacer" />
        <span className="tiny muted">Reversed decisions and open disagreements</span>
      </div>
      {items.length === 0 ? <div className="empty">No contradictions between meetings.</div> : (
        <div className="list">
          {items.map((c) => <Card key={c.id} c={c} live={live} curDate={date(c.meeting_id)}
                                  prevDate={c.previous_meeting_id ? date(c.previous_meeting_id) : "Earlier (per these notes)"} />)}
        </div>
      )}
    </div>
  );
}

function Card({ c, curDate, prevDate, live }: { c: Conflict; curDate: string; prevDate: string; live: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (action: string) => {
    setBusy(true); setErr(null);
    try { await api(`contradictions/${c.id}/resolve`, "POST", { action }); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const disagreement = c.source === "disagreement";
  const found = disagreement ? "People in this meeting disagree; nothing was decided"
    : c.source !== "cross_meeting" ? "Stated in the notes themselves"
    : live ? "Matched across meetings by Qualcomm embeddings, confirmed by the chat model"
    : "Matched by the replay engine (no Qualcomm key)";
  return (
    <div className="list-item" id={`conflict-${c.id}`}>
      <div className="row between">
        <div className="row" style={{ gap: 6 }}>
          <span className="task-title" style={{ textTransform: "capitalize" }}>{c.topic}</span>
          <span className="tag tag-neutral">{disagreement ? "Disagreement" : "Reversal"}</span>
        </div>
        <span className={`tag ${c.status === "open" ? "tag-red" : "tag-ok"}`}>{disagreement && c.status === "confirmed_current" ? `Kept ${c.current}` : disagreement && c.status === "reverted" ? `Kept ${c.previous}` : RESOLVED[c.status]}{c.resolved_by ? ` · ${c.resolved_by}` : ""}</span>
      </div>
      <div className="versus">
        <div><span className="when">{disagreement ? "One view" : `This meeting · ${curDate}`}</span><span className="what">{c.current}</span><span className="quote small">{c.current_evidence}</span></div>
        <div className={disagreement ? "" : "is-old"}><span className="when">{disagreement ? "Other view" : `Before · ${prevDate}`}</span><span className="what">{c.previous}</span><span className="quote small">{c.previous_evidence}</span></div>
      </div>
      {c.status === "open" && (
        <div className="row">
          <button className="btn btn-primary" disabled={busy} onClick={() => act("confirm_current")}>Keep {c.current}</button>
          <button className="btn" disabled={busy} onClick={() => act("revert")}>{disagreement ? `Keep ${c.previous}` : `Revert to ${c.previous}`}</button>
          <div className="spacer" />
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act("follow_up")}>Follow-up meeting</button>
        </div>
      )}
      <div className="why"><Icon name="info" size={13} />{found}</div>
      {err && <div className="alert alert-error">{err}</div>}
    </div>
  );
}
