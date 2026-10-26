"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Item, ManagerState, useLiveState } from "@/lib/api";
import Conflicts from "./Conflicts";
import Flowchart from "./Flowchart";
import { ActionTable, Callout, ExtractBox, NeedsReview, StatsBar, TeamStrip } from "./Panels";
import { Bell, EvidenceDrawer, TopBar } from "./Shell";

type Person = { name: string; email: string; team: string; role: string };
type Demo = { label: string; date: string; notes: string };

export default function ManagerDashboard() {
  const { state, error } = useLiveState<ManagerState>();
  const [people, setPeople] = useState<Person[]>([]);
  const [demos, setDemos] = useState<Demo[]>([]);
  const [evidence, setEvidence] = useState<Item | null>(null);

  useEffect(() => {
    fetch("/api/people").then((r) => r.json()).then(setPeople).catch(() => setPeople([]));
    api<Demo[]>("demo-notes").then(setDemos).catch(() => setDemos([]));
  }, []);
  const openEvidence = useCallback((i: Item) => setEvidence(i), []);

  if (!state) {
    return <div className="page">{error ? <div className="alert alert-error">{error}</div> : <p className="muted">Loading dashboard…</p>}</div>;
  }
  const s = state;
  return (
    <>
      <TopBar ai={s.ai} me={s.me} today={s.today} simulated={s.simulated}
              bell={<Bell items={s.notifications} unread={s.unread} onRead={() => api("notifications/read", "POST", {})} />} />
      <main className="page stack">
        {error && <div className="alert alert-error">{error}</div>}
        <StatsBar stats={s.stats} />
        <div className="grid-main">
          <div className="stack">
            <Callout c={s.callout} />
            <section className="card">
              <h2>Cross-team dependency flowchart</h2>
              <Flowchart graph={s.graph} onOpen={openEvidence} />
            </section>
            <TeamStrip teams={s.teams} />
          </div>
          <div className="stack">
            <ExtractBox model={s.ai.model} live={s.ai.mode === "live"} demos={demos} />
            <Conflicts items={s.conflicts} meetings={s.meetings} live={s.ai.mode === "live"} />
            <section className="card" aria-labelledby="nr">
              <h2 id="nr">Needs Review <span className="chip chip-review">{s.needs_review.length}</span></h2>
              <NeedsReview items={s.needs_review} people={people} onEvidence={openEvidence} />
            </section>
          </div>
        </div>
        <section className="card">
          <h2>Action items</h2>
          <ActionTable actions={s.actions} onEvidence={openEvidence} />
        </section>
        <div className="grid-main">
          <section className="card">
            <h2>Decisions</h2>
            {s.decisions.length ? (
              <table><tbody>{s.decisions.map((d) => (
                <tr key={d.id}><td style={d.review_state === "superseded" ? { textDecoration: "line-through", color: "var(--faint)" } : undefined}>{d.text}{d.review_state === "superseded" && <> <span className="chip chip-grey">superseded</span></>}<div className="faint" style={{ fontSize: 11.5 }}>{d.meeting.topic} · {d.meeting.date}</div></td>
                  <td><button className="btn-link" onClick={() => openEvidence(d)}>view source</button></td></tr>
              ))}</tbody></table>
            ) : <p className="muted">None yet.</p>}
          </section>
          <section className="card">
            <h2>Risks</h2>
            {s.risks.length ? (
              <table><tbody>{s.risks.map((r) => (
                <tr key={r.id}><td>{r.text}<div className="faint" style={{ fontSize: 11.5 }}>Owner: {r.owner ?? "UNKNOWN"} · severity {r.severity?.toLowerCase() ?? "unknown"}</div></td>
                  <td><button className="btn-link" onClick={() => openEvidence(r)}>view source</button></td></tr>
              ))}</tbody></table>
            ) : <p className="muted">None yet.</p>}
          </section>
        </div>
        {s.meetings.length > 0 && (
          <section className="card">
            <h2>Ingested meetings</h2>
            <table>
              <thead><tr><th>Meeting</th><th>Date</th><th>Model</th><th>Calls</th><th>Rejected claims</th></tr></thead>
              <tbody>{s.meetings.map((m) => (
                <tr key={m.id}><td>{m.topic}</td><td>{m.meeting_date}</td><td className="mono">{m.model}</td><td>{m.attempts}</td>
                  <td>{m.rejected.length ? m.rejected.map((r) => `${r.text}: ${r.reason}`).join("; ") : <span className="faint">none</span>}</td></tr>
              ))}</tbody>
            </table>
          </section>
        )}
      </main>
      {evidence && (
        <EvidenceDrawer meetingId={evidence.meeting_id} start={evidence.ev_start} end={evidence.ev_end}
                        title={`${evidence.text} · owner ${evidence.owner ?? "UNKNOWN"}`} onClose={() => setEvidence(null)} />
      )}
    </>
  );
}
