"use client";

import { useState } from "react";
import { api, ApiError, Email, fmtDate } from "@/lib/api";
import Icon from "./Icon";

type CheckResult = { today: string; newly_overdue: string[]; newly_at_risk: string[]; emails: string[] };

export default function DemoControls({ today, simulated, emails }: { today: string; simulated: boolean; emails: Email[] }) {
  const [date, setDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async (path: string, body: unknown) => {
    setBusy(true); setMsg(null);
    try {
      const r = await api<CheckResult>(path, "POST", body);
      const parts = [`Checked as of ${fmtDate(r.today)}.`];
      parts.push(r.newly_overdue.length ? `Now overdue: ${r.newly_overdue.join(", ")}.` : "No new overdue tasks.");
      if (r.newly_at_risk.length) parts.push(`Now at risk: ${r.newly_at_risk.join(", ")}.`);
      if (r.emails.length) parts.push(`${r.emails.length} email${r.emails.length === 1 ? "" : "s"} queued.`);
      setMsg(parts.join(" "));
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" id="deadlines">
      <div className="card-head">
        <h2>Deadline check</h2>
        <div className="spacer" />
        <span className="tiny muted">Runs automatically every hour</span>
      </div>
      <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="row">
          <button className="btn" onClick={() => run("admin/run-check", {})} disabled={busy}><Icon name="clock" size={14} />Run now</button>
          <span className="muted small" style={{ margin: "0 4px" }}>or check as of</span>
          <input className="input" type="date" aria-label="Simulated date" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 150 }} />
          <button className="btn btn-primary" onClick={() => run("admin/clock", { date })} disabled={busy || !date}>Simulate date</button>
          {simulated && <button className="btn btn-ghost" onClick={() => run("admin/clock", { date: null })} disabled={busy}>Use real date</button>}
        </div>
        {msg && <div className="alert alert-info" role="status"><Icon name="info" size={15} />{msg}</div>}
      </div>
      {emails.length > 0 && (
        <table className="table">
          <thead><tr><th>Email</th><th>Recipient</th><th>Status</th></tr></thead>
          <tbody>
            {emails.slice(0, 6).map((e) => (
              <tr key={e.id}>
                <td><div className="row" style={{ gap: 6 }}><Icon name="mail" size={14} className="muted" />{e.subject}</div></td>
                <td className="small">{e.to_email}{e.delivered_to && e.delivered_to !== e.to_email && <div className="tiny muted">delivered to {e.delivered_to}</div>}</td>
                <td><span className={`status ${e.status === "sent" ? "s-green" : e.status === "failed" ? "s-red" : "s-grey"}`}><i />{e.status}</span>
                  {e.error && <div className="tiny muted">{e.error}</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
