"use client";

import { useState } from "react";
import { api, ApiError, Conflict, fmtDate, Meeting } from "@/lib/api";

const STATUS: Record<Conflict["status"], string> = {
  open: "Open", confirmed_current: "Current decision confirmed", reverted: "Reverted to previous", follow_up: "Follow-up meeting",
};

export default function Conflicts({ items, meetings, live }: { items: Conflict[]; meetings: Meeting[]; live: boolean }) {
  if (!items.length) return null;
  const date = (id: string | null) => fmtDate(meetings.find((m) => m.id === id)?.meeting_date ?? null);
  const open = items.filter((c) => c.status === "open").length;
  return (
    <section className="card" aria-labelledby="cf-h" style={{ borderColor: open ? "#6b4a1c" : undefined }}>
      <h2 id="cf-h">Decision conflicts {open > 0 && <span className="chip chip-orange">{open} open</span>}</h2>
      <div className="stack">
        {items.map((c) => <Card key={c.id} c={c} prevDate={c.previous_meeting_id ? date(c.previous_meeting_id) : "earlier (stated in these notes)"} curDate={date(c.meeting_id)} live={live} />)}
      </div>
    </section>
  );
}

function Card({ c, prevDate, curDate, live }: { c: Conflict; prevDate: string; curDate: string; live: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (action: string) => {
    setBusy(true); setErr(null);
    try { await api(`contradictions/${c.id}/resolve`, "POST", { action }); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  return (
    <div className="conflict" id={`conflict-${c.id}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong style={{ fontSize: 15 }}>{c.topic}</strong>
        <span className={`chip ${c.status === "open" ? "chip-orange" : "chip-green"}`}>{STATUS[c.status]}{c.resolved_by ? ` · ${c.resolved_by}` : ""}</span>
      </div>
      <p className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>This contradicts an earlier decision.{c.explanation ? ` ${c.explanation}` : ""}</p>
      <div className="vs">
        <div><span className="faint" style={{ fontSize: 11.5 }}>NOW · {curDate}</span><b>{c.current}</b><span className="evidence">“{c.current_evidence}”</span></div>
        <div><span className="faint" style={{ fontSize: 11.5 }}>BEFORE · {prevDate}</span><b>{c.previous}</b><span className="evidence">“{c.previous_evidence}”</span></div>
      </div>
      {c.status === "open" && (
        <div className="row">
          <button className="btn-gold" disabled={busy} onClick={() => act("confirm_current")}>Confirm {c.current}</button>
          <button disabled={busy} onClick={() => act("revert")}>Revert to {c.previous}</button>
          <button disabled={busy} onClick={() => act("follow_up")}>Needs follow-up meeting</button>
        </div>
      )}
      <p className="faint" style={{ fontSize: 11.5, marginTop: 8 }}>
        {c.source !== "cross_meeting" ? "Stated in the notes themselves." : live ? "Found by Qualcomm embeddings + reranker across meetings, confirmed by the chat model." : "Found by the dev replay stand-ins (no Qualcomm key): not a Qualcomm result."}
      </p>
      {err && <div className="alert alert-error">{err}</div>}
    </div>
  );
}
