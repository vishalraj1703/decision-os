"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, Item, ManagerState, Meeting, useLiveState } from "@/lib/api";
import Conflicts from "./Conflicts";
import DemoControls from "./DemoControls";
import Flowchart, { Legend } from "./Flowchart";
import Icon from "./Icon";
import { ActionTable, Callout, Metrics, NeedsReview, NewMeeting, TeamStatus } from "./Panels";
import { Bell, EnginePill, NavLink, SimPill, Sidebar, SourceSheet, UserMenu } from "./Shell";
import { AICallLog, SelfCheck, SelfCheckSummary, TrustReceipt } from "./Trust";

type Person = { name: string; email: string; team: string; role: string };
type Demo = { label: string; date: string; notes: string };

export default function ManagerDashboard() {
  const { state, error } = useLiveState<ManagerState>();
  const [people, setPeople] = useState<Person[]>([]);
  const [demos, setDemos] = useState<Demo[]>([]);
  const [source, setSource] = useState<Item | null>(null);
  const [adding, setAdding] = useState(false);
  const [check, setCheck] = useState<Meeting | null>(null);

  useEffect(() => {
    fetch("/api/people").then((r) => r.json()).then(setPeople).catch(() => setPeople([]));
    api<Demo[]>("demo-notes").then(setDemos).catch(() => setDemos([]));
  }, []);
  const openSource = useCallback((i: Item) => setSource(i), []);

  if (!state) {
    return <div className="content">{error ? <div className="alert alert-error">{error}</div> : <div className="row muted"><span className="spinner dark" />Loading…</div>}</div>;
  }
  const s = state;
  const openConflicts = s.conflicts.filter((c) => c.status === "open").length;
  const live = s.ai.mode === "live";

  return (
    <div className="shell">
      <Sidebar ai={s.ai}>
        <nav className="nav" aria-label="Sections">
          <div className="nav-title">Workspace</div>
          <NavLink href="#top" icon="layout" label="Overview" />
          <NavLink href="#review" icon="inbox" label="Needs review" count={s.needs_review.length} />
          <NavLink href="#conflicts" icon="split" label="Conflicts" count={openConflicts} alert />
          <NavLink href="#actions" icon="list" label="Action items" count={s.actions.length} />
          <NavLink href="#decisions" icon="checkCircle" label="Decisions & risks" />
          <NavLink href="#meetings" icon="file" label="Meetings" count={s.meetings.length} />
          <NavLink href="#ai-log" icon="sparkle" label="AI call log" />
          <NavLink href="#deadlines" icon="clock" label="Deadline check" />
        </nav>
      </Sidebar>

      <div className="main" id="top">
        <header className="topbar">
          <div className="title">
            <h1 style={{ fontSize: 16 }}>Overview</h1>
            <span>{s.meetings.length ? `${s.meetings.length} meeting${s.meetings.length === 1 ? "" : "s"} · last on ${fmtDate(s.meetings[s.meetings.length - 1].meeting_date)}` : "No meetings yet"}</span>
          </div>
          <div className="spacer" />
          <SimPill today={s.today} simulated={s.simulated} />
          <EnginePill ai={s.ai} />
          <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" size={15} />New meeting</button>
          <Bell items={s.notifications} unread={s.unread} />
          <UserMenu me={s.me} />
        </header>

        <main className="content">
          {error && <div className="alert alert-error"><Icon name="alert" size={15} />{error}</div>}
          <Metrics stats={s.stats} actions={s.actions} />
          <Callout c={s.callout} />

          <div className="grid-2">
            <div className="col">
              <div className="card">
                <div className="card-head">
                  <h2>Dependencies</h2>
                  <span className="sub">who is waiting on whom</span>
                  <div className="spacer" />
                  <Legend />
                </div>
                <Flowchart graph={s.graph} onOpen={openSource} />
              </div>
              <TeamStatus teams={s.teams} />
            </div>
            <div className="col">
              <NeedsReview items={s.needs_review} people={people} onSource={openSource} />
              <Conflicts items={s.conflicts} meetings={s.meetings} live={live} />
            </div>
          </div>

          <ActionTable actions={s.actions} onSource={openSource} />

          <div className="grid-2-even" id="decisions">
            <div className="card">
              <div className="card-head"><h2>Decisions</h2><span className="sub num">{s.decisions.length}</span></div>
              {s.decisions.length === 0 ? <div className="empty">No decisions recorded.</div> : (
                <div className="list">{s.decisions.map((d) => (
                  <div key={d.id} className="list-item" style={{ gap: 4 }}>
                    <div className="row between">
                      <span className="task-title" style={d.review_state === "superseded" ? { textDecoration: "line-through", color: "var(--muted)" } : undefined}>{d.text}</span>
                      {d.review_state === "superseded" ? <span className="tag tag-neutral">Superseded</span> : <span className="tiny muted">{fmtDate(d.meeting.date)}</span>}
                    </div>
                    <TrustReceipt i={d} />
                    <div className="small"><span className="quote">{d.evidence_quote}</span> <button className="link" onClick={() => openSource(d)}>View source</button></div>
                  </div>
                ))}</div>
              )}
            </div>
            <div className="card">
              <div className="card-head"><h2>Risks</h2><span className="sub num">{s.risks.length}</span></div>
              {s.risks.length === 0 ? <div className="empty">No risks recorded.</div> : (
                <div className="list">{s.risks.map((r) => (
                  <div key={r.id} className="list-item" style={{ gap: 4 }}>
                    <div className="row between">
                      <span className="task-title">{r.text}</span>
                      {r.severity && r.severity !== "UNKNOWN" && <span className={`tag ${r.severity === "high" ? "tag-red" : "tag-neutral"}`} style={{ textTransform: "capitalize" }}>{r.severity}</span>}
                    </div>
                    <div className="row between"><span className="small muted">Owner: {r.owner ?? <span className="unknown">not stated</span>}</span><TrustReceipt i={r} /></div>
                    <div className="small"><span className="quote">{r.evidence_quote}</span> <button className="link" onClick={() => openSource(r)}>View source</button></div>
                  </div>
                ))}</div>
              )}
            </div>
          </div>

          <div className="card" id="meetings">
            <div className="card-head"><h2>Meetings</h2><span className="sub num">{s.meetings.length}</span><div className="spacer" />
              <button className="btn btn-sm" onClick={() => setAdding(true)}><Icon name="plus" size={13} />Add</button></div>
            {s.meetings.length === 0 ? <div className="empty">No meetings yet. Add notes to get started.</div> : (
              <table className="table">
                <thead><tr><th>Meeting</th><th>Date</th><th>Engine</th><th>Model calls</th><th>Self-check</th></tr></thead>
                <tbody>{[...s.meetings].reverse().map((m) => (
                  <tr key={m.id}>
                    <td className="task-title">{m.topic}</td>
                    <td className="num">{fmtDate(m.meeting_date)}</td>
                    <td className="mono">{m.model}</td>
                    <td className="num">{m.attempts + (m.verify.attempts ?? 0)}</td>
                    <td><SelfCheckSummary m={m} onOpen={() => setCheck(m)} /></td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>

          <AICallLog calls={s.ai_calls} meetings={s.meetings} />

          <DemoControls today={s.today} simulated={s.simulated} emails={s.emails} />
        </main>
      </div>

      {check && <SelfCheck m={s.meetings.find((m) => m.id === check.id) ?? check} onClose={() => setCheck(null)} />}
      {adding && <NewMeeting demos={demos} model={s.ai.model} live={live} onClose={() => setAdding(false)} />}
      {source && (
        <SourceSheet meetingId={source.meeting_id} start={source.ev_start} end={source.ev_end} title={source.text}
                     subtitle={`${source.kind === "action" ? "Task" : source.kind === "risk" ? "Risk" : "Decision"} · owner ${source.owner ?? "not stated"}`}
                     onClose={() => setSource(null)} />
      )}
    </div>
  );
}
