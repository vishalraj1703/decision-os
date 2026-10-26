"use client";

import { useState } from "react";
import { api, ApiError, Email, fmtDate } from "@/lib/api";

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
      parts.push(r.newly_overdue.length ? `Newly overdue: ${r.newly_overdue.join(", ")}.` : "No new overdue tasks.");
      if (r.newly_at_risk.length) parts.push(`Now at risk: ${r.newly_at_risk.join(", ")}.`);
      if (r.emails.length) parts.push(`Emails: ${r.emails.length}.`);
      setMsg(parts.join(" "));
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card" aria-labelledby="dc-h">
      <h2 id="dc-h">Deadline check</h2>
      <p className="faint" style={{ fontSize: 12.5 }}>The scheduler checks deadlines every hour. For the demo, run it now, or simulate a later date to show the cascade.</p>
      <div className="row">
        <button onClick={() => run("admin/run-check", {})} disabled={busy}>Run check now</button>
        <input type="date" aria-label="Simulated date" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 160 }} />
        <button className="btn-gold" onClick={() => run("admin/clock", { date })} disabled={busy || !date}>Simulate this date</button>
        {simulated && <button onClick={() => run("admin/clock", { date: null })} disabled={busy}>Back to real time</button>}
      </div>
      {msg && <div className="alert alert-ok" style={{ marginTop: 10 }} role="status">{msg}</div>}
      {emails.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Recent emails</h3>
          <table>
            <tbody>
              {emails.slice(0, 6).map((e) => (
                <tr key={e.id}>
                  <td style={{ width: 90 }}><span className={`chip ${e.status === "sent" ? "chip-green" : e.status === "failed" ? "chip-red" : "chip-grey"}`}>{e.status}</span></td>
                  <td>{e.subject}<div className="faint" style={{ fontSize: 11.5 }}>to {e.to_email}{e.delivered_to && e.delivered_to !== e.to_email ? ` (delivered to ${e.delivered_to})` : ""}{e.error ? ` · ${e.error}` : ""}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
