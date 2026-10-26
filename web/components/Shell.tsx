"use client";

import { signOut } from "next-auth/react";
import { useEffect, useRef, useState } from "react";
import { AIStatus, api, fmtDate, Notification } from "@/lib/api";

export function AIBadge({ ai }: { ai: AIStatus }) {
  if (ai.mode === "live") {
    return <span className="badge badge-live" title="Every AI call goes to Qualcomm Cloud AI Playground">Qualcomm Cloud AI · {ai.model}</span>;
  }
  return <span className="badge badge-replay" title={ai.reason}>Replay (dev) · no Qualcomm key</span>;
}

export function Bell({ items, unread, onRead }: { items: Notification[]; unread: number; onRead: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div className="bell" ref={ref}>
      <button aria-label={`Notifications, ${unread} unread`} aria-expanded={open}
              onClick={() => { setOpen(!open); if (!open && unread) onRead(); }}
              style={unread ? { borderColor: "var(--red)" } : undefined}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {unread > 0 && <span className="bell-count">{unread}</span>}
      </button>
      {open && (
        <div className="bell-panel" role="dialog" aria-label="Notifications">
          {items.length === 0 && <div className="bell-item muted">Nothing yet.</div>}
          {items.map((n) => (
            <div key={n.id} className={`bell-item${n.read ? "" : " unread"}`}>
              <div>{n.text}</div>
              <div className="faint" style={{ fontSize: 11.5, marginTop: 2 }}>
                {new Date(n.created_at).toLocaleString()} {n.link && <a href={n.link} onClick={() => setOpen(false)}>open</a>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopBar({ ai, me, today, simulated, bell }: {
  ai: AIStatus; me: { name: string; role: string; team: string }; today: string; simulated: boolean; bell: React.ReactNode;
}) {
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark">DO</span>Decision OS</div>
      <AIBadge ai={ai} />
      {simulated && <span className="badge badge-sim" title="Demo clock: the deadline check runs as if today were this date">Simulated date: {fmtDate(today)}</span>}
      <div className="spacer" />
      {bell}
      <span className="muted" style={{ fontSize: 13 }}>{me.name} · {me.role === "manager" ? "Manager" : me.team}</span>
      <button className="btn-small" onClick={() => signOut({ callbackUrl: "/login" })}>Sign out</button>
    </header>
  );
}

export function EvidenceDrawer({ meetingId, start, end, title, onClose }: {
  meetingId: string; start: number; end: number; title: string; onClose: () => void;
}) {
  const [src, setSrc] = useState<{ notes: string; topic: string; meeting_date: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const markRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    api<{ notes: string; topic: string; meeting_date: string }>(`meetings/${meetingId}/source`).then(setSrc).catch((e) => setErr(e.message));
  }, [meetingId]);
  useEffect(() => {
    closeRef.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  useEffect(() => { markRef.current?.scrollIntoView({ block: "center" }); }, [src]);
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Source notes">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Source sentence</h2>
          <button ref={closeRef} onClick={onClose}>Close</button>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>{title}</p>
        {err && <div className="alert alert-error">{err}</div>}
        {src && (
          <>
            <p className="faint" style={{ fontSize: 13 }}>{src.topic} · meeting of {fmtDate(src.meeting_date)}. The highlighted sentence is the exact text the item was extracted from.</p>
            <div className="source">
              {src.notes.slice(0, start)}
              <mark ref={markRef}>{src.notes.slice(start, end)}</mark>
              {src.notes.slice(end)}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
