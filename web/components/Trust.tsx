"use client";

import { useEffect, useRef } from "react";
import { Accuracy, AICall, fmtDate, Item, Meeting, ReplayRow } from "@/lib/api";
import Icon from "./Icon";

/** Quote found in the notes, meaning confirmed by the Verifier, and the model's own confidence. */
export function TrustReceipt({ i }: { i: Item }) {
  const v = i.verification;
  const pct = Math.round(i.confidence * 100);
  const meaning = v?.supported === true ? "ok" : v?.supported === false ? "bad" : "none";
  const title = [
    "Quote found: the sentence is in the notes (checked in code).",
    meaning === "ok" ? `Meaning verified: the Verifier (${v?.by ?? "model"}) re-read the notes and confirmed this item.`
      : `Meaning not checked: ${v?.note ?? "this item was not verified."}`,
    `Confidence ${pct}%: self-reported by the model, not a measured accuracy.`,
    ...(i.evidence_hash ? [`Evidence fingerprint: ${i.evidence_hash}`] : []),
  ].join("\n");
  return (
    <span className="receipt" title={title} aria-label={title}>
      <span className={`rc ${v?.quote_found === false ? "rc-none" : "rc-ok"}`}><Icon name="check" size={12} strokeWidth={2.4} />quote</span>
      <span className={`rc rc-${meaning}`}>{meaning === "ok" ? <Icon name="check" size={12} strokeWidth={2.4} /> : <span aria-hidden>–</span>}meaning</span>
      <span className="num">{(i.confidence).toFixed(2)}</span>
    </span>
  );
}

function selfCheckCounts(m: Meeting) {
  const removed = m.replay.filter((r) => r.outcome === "removed").length;
  const corrected = m.replay.filter((r) => r.outcome === "corrected").length;
  return { removed, corrected };
}

export function SelfCheckSummary({ m, onOpen }: { m: Meeting; onOpen: () => void }) {
  if (!m.replay.length) return <span className="faint small">Not recorded</span>;
  const { removed, corrected } = selfCheckCounts(m);
  const parts = [removed && `${removed} removed`, corrected && `${corrected} corrected`].filter(Boolean);
  return (
    <span className="row" style={{ gap: 8 }}>
      <span className="small">{parts.length ? parts.join(" · ") : <span className="muted">No changes</span>}</span>
      <button className="link" onClick={onOpen}>View</button>
    </span>
  );
}

const WHO: Record<string, string> = { verifier: "Verifier", code: "Code check" };

function Field({ label, value, changed }: { label: string; value: string; changed?: boolean }) {
  const unknown = value === "UNKNOWN";
  return (
    <div className="tiny">
      <span className="muted">{label} </span>
      <span className={changed ? "chg" : unknown ? "unknown" : ""}>{unknown ? "UNKNOWN" : value}</span>
    </div>
  );
}

function Row({ r }: { r: ReplayRow }) {
  const kind = r.kind === "action" ? "Task" : r.kind === "risk" ? "Risk" : "Decision";
  const reasons = r.reasons.filter((x) => r.outcome !== "kept" || x.by === "verifier");
  return (
    <div className={`replay-row is-${r.outcome}`}>
      <div className="replay-cell">
        <div className="tiny muted" style={{ fontWeight: 600 }}>{kind}</div>
        <div className="task-title">{r.text}</div>
        <Field label="Owner" value={r.owner} />
        {r.kind === "action" && <Field label="Due" value={r.deadline} />}
      </div>
      <div className="replay-cell">
        {r.outcome === "removed" ? (
          <>
            <div className="tiny" style={{ fontWeight: 600, color: "var(--red)" }}>Removed</div>
            <div className="task-title struck">{r.text}</div>
          </>
        ) : (
          <>
            <div className="tiny" style={{ fontWeight: 600, color: r.outcome === "corrected" ? "var(--amber)" : "var(--green)" }}>
              {r.outcome === "corrected" ? "Corrected" : "Kept"}
            </div>
            <div className="task-title">{r.text}</div>
            <Field label="Owner" value={r.final!.owner} changed={r.final!.owner !== r.owner} />
            {r.kind === "action" && <Field label="Due" value={r.final!.deadline} changed={r.final!.deadline !== r.deadline} />}
          </>
        )}
        {reasons.map((x, n) => (
          <div key={n} className="why"><span className={`tag ${x.by === "verifier" ? "tag-accent" : "tag-neutral"}`}>{WHO[x.by] ?? x.by}</span>{x.text}</div>
        ))}
      </div>
    </div>
  );
}

const MASKED: Record<string, [string, string]> = { email: ["email", "emails"], phone: ["phone number", "phone numbers"], id: ["ID number", "ID numbers"] };

/** Pass 1 beside the verified result: what the model said first, and what the checks changed. */
export function SelfCheck({ m, onClose }: { m: Meeting; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const { removed, corrected } = selfCheckCounts(m);
  const masked = Object.entries(m.redactions).map(([k, n]) => `${n} ${MASKED[k]?.[n === 1 ? 0 : 1] ?? k}`);
  const v = m.verify;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="sheet sheet-wide" role="dialog" aria-modal="true" aria-labelledby="sc-title">
        <div className="sheet-head">
          <div style={{ flex: 1 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Self-check · {fmtDate(m.meeting_date)}</div>
            <h2 id="sc-title" style={{ fontSize: 16, marginTop: 2 }}>{m.topic}</h2>
            <div className="small muted" style={{ marginTop: 2 }}>
              {m.replay.length} claims from pass 1 · {removed} removed · {corrected} corrected
            </div>
          </div>
          <button ref={closeRef} className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        </div>
        <div className="sheet-body">
          {v.status === "failed" && <div className="alert alert-warn"><Icon name="alert" size={15} />The Verifier did not answer for this meeting, so items were kept without a meaning check.</div>}
          {v.status === "skipped" && m.replay.length > 0 && <div className="alert alert-info"><Icon name="info" size={15} />The Verifier was off for this meeting. Only the code checks ran.</div>}
          <div className="small muted">
            {masked.length ? `Masked before the AI saw the notes: ${masked.join(", ")}. ` : "No emails or phone numbers to mask. "}
            Pass 1 is the Extractor&apos;s reply ({m.model}). Code checks confirm each quote and owner is in the notes; the Verifier
            {v.model ? ` (${v.model})` : ""} re-reads the notes and judges meaning.
          </div>
          <div className="replay">
            <div className="replay-row replay-head"><div className="replay-cell">Pass 1: Extractor</div><div className="replay-cell">Pass 2: Verified</div></div>
            {m.replay.map((r, n) => <Row key={n} r={r} />)}
          </div>
        </div>
      </aside>
    </>
  );
}

const PURPOSE: Record<string, string> = {
  extract: "Extract", "extract retry": "Extract retry", verify: "Verify", conflict: "Conflict check",
  callout: "Callout", embed: "Embeddings", rerank: "Rerank", chat: "Chat",
};

export function AICallLog({ calls, meetings }: { calls: AICall[]; meetings: Meeting[] }) {
  const topic = new Map(meetings.map((m) => [m.id, m.topic]));
  return (
    <div className="card" id="ai-log">
      <div className="card-head">
        <h2>AI call log</h2><span className="sub num">{calls.length ? `last ${calls.length}` : ""}</span>
        <div className="spacer" />
        <span className="tiny muted">Model, latency and verdict. Never the notes.</span>
      </div>
      {calls.length === 0 ? <div className="empty">No AI calls yet.</div> : (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th>When</th><th>Call</th><th>Meeting</th><th>Model</th><th>Latency</th><th>Verdict</th></tr></thead>
            <tbody>{calls.map((c) => (
              <tr key={c.id}>
                <td className="num tiny">{new Date(c.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</td>
                <td>{PURPOSE[c.purpose] ?? c.purpose}</td>
                <td className="small">{c.meeting_id ? topic.get(c.meeting_id) ?? <span className="faint">not saved</span> : <span className="faint">—</span>}</td>
                <td className="mono tiny">{c.model || "—"}</td>
                <td className="num">{c.latency_ms != null ? `${(c.latency_ms / 1000).toFixed(1)} s` : "—"}</td>
                <td><span className={`status ${c.ok ? "s-green" : "s-red"}`}><i />{c.verdict ?? (c.ok ? "ok" : "failed")}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function pctText(v: number | null | undefined) {
  return v == null ? "–" : `${Math.round(v * 100)}%`;
}

/** Recorded run of the 10-note gold set: one prompt vs the full pipeline. Read-only. */
export function Scoreboard({ a }: { a: Accuracy | null }) {
  const order: [keyof Accuracy["layers"], string][] = [["pass1", "Pass 1 alone"], ["code", "+ code checks"], ["full", "+ Verifier"]];
  return (
    <div className="card" id="accuracy">
      <div className="card-head">
        <h2>Accuracy scoreboard</h2>
        <span className="sub">{a ? `${a.notes} hand-labelled notes · ${a.gold_items} answers` : "gold set"}</span>
      </div>
      {!a ? (
        <div className="empty">Not measured yet. Run <span className="mono">scripts/eval_gold.py</span> with a Qualcomm key to record the numbers.</div>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="table score-table">
              <thead><tr><th>Measured on the gold set</th>{order.map(([k, l]) => <th key={k} className={k === "full" ? "is-ours" : ""}>{l}</th>)}</tr></thead>
              <tbody>
                <tr><td>Precision <div className="tiny muted">extracted items that are right</div></td>
                  {order.map(([k]) => <td key={k} className={`num ${k === "full" ? "is-ours" : ""}`}>{pctText(a.layers[k].precision)}</td>)}</tr>
                <tr><td>Recall <div className="tiny muted">answers that were found</div></td>
                  {order.map(([k]) => <td key={k} className={`num ${k === "full" ? "is-ours" : ""}`}>{pctText(a.layers[k].recall)}</td>)}</tr>
                <tr><td>Hallucinations <div className="tiny muted">invented items, owners or dates</div></td>
                  {order.map(([k]) => <td key={k} className={`num ${k === "full" ? "is-ours" : ""}`}><b>{a.layers[k].hallucinations}</b>
                    <span className="tiny muted"> ({pctText(a.layers[k].hallucination_rate)})</span></td>)}</tr>
              </tbody>
            </table>
          </div>
          {a.caught.length > 0 && (
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="tiny muted" style={{ fontWeight: 600 }}>Caught by the checks ({a.caught_total})</div>
              {a.caught.map((c, n) => (
                <div key={n} className="why"><Icon name="check" size={13} /><span><b>{c.text}</b> · {c.why} <span className="faint">({c.note})</span></span></div>
              ))}
            </div>
          )}
          {(a.lost?.length ?? 0) > 0 && (
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 0 }}>
              <div className="tiny muted" style={{ fontWeight: 600 }}>Right answers the Verifier removed ({a.lost_total})</div>
              {a.lost!.map((c, n) => (
                <div key={n} className="why"><Icon name="x" size={13} /><span><b>{c.text}</b> · {c.why} <span className="faint">({c.note})</span></span></div>
              ))}
            </div>
          )}
          <div className="card-foot">
            Recorded run with {a.model} on {new Date(a.measured_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}, not live.
            {" "}{a.remaining} mistake{a.remaining === 1 ? " remains" : "s remain"} after all checks.
            {a.failed_notes.length > 0 && ` ${a.failed_notes.length} note${a.failed_notes.length === 1 ? "" : "s"} failed and count as nothing found.`}
            {" "}Ten notes show the direction, not a precise accuracy.
          </div>
        </>
      )}
    </div>
  );
}
