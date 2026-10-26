"use client";

import { signOut } from "next-auth/react";
import { useEffect, useRef, useState } from "react";
import { AIStatus, api, fmtDate, Notification } from "@/lib/api";
import Icon from "./Icon";

export function initials(name: string) {
  return name.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function ago(iso: string) {
  const s = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function EnginePill({ ai }: { ai: AIStatus }) {
  if (ai.mode === "live") return <span className="pill pill-live" title="All AI calls go to Qualcomm Cloud AI Playground"><span className="dot" />Qualcomm Cloud AI</span>;
  return <span className="pill pill-replay" title={ai.reason}><span className="dot" />Replay mode</span>;
}

export function Bell({ items, unread }: { items: Notification[]; unread: number }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const toggle = () => {
    setOpen(!open);
    if (!open && unread) api("notifications/read", "POST", {}).catch(() => undefined);
  };
  return (
    <div className="bell" ref={ref}>
      <button className="btn btn-ghost btn-icon" aria-label={`Notifications, ${unread} unread`} aria-expanded={open} onClick={toggle}>
        <Icon name="bell" size={17} />
        {unread > 0 && <span className="badge-count num">{unread}</span>}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Notifications">
          <div className="popover-head"><h2>Notifications</h2><span className="tiny muted">{items.length} total</span></div>
          {items.length === 0 && <div className="empty">You're all caught up.</div>}
          {items.map((n) => (
            <div key={n.id} className={`note-item${n.read ? "" : " unread"}`}>
              <span className="d" />
              <div>
                {n.link ? <a href={n.link} onClick={() => setOpen(false)} style={{ color: "var(--text)" }}>{n.text}</a> : n.text}
                <time dateTime={n.created_at}>{ago(n.created_at)}</time>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function UserMenu({ me }: { me: { name: string; role: string; team: string } }) {
  return (
    <div className="row" style={{ gap: 4 }}>
      <div className="user">
        <span className="avatar">{initials(me.name)}</span>
        <div className="who">{me.name}<span>{me.role === "manager" ? "Manager" : me.team}</span></div>
      </div>
      <button className="btn btn-ghost btn-icon" aria-label="Sign out" title="Sign out" onClick={() => signOut({ callbackUrl: "/login" })}>
        <Icon name="logout" />
      </button>
    </div>
  );
}

export function NavLink({ href, icon, label, count, alert }: { href: string; icon: string; label: string; count?: number; alert?: boolean }) {
  return (
    <a href={href}>
      <Icon name={icon} size={15} />
      {label}
      {count !== undefined && count > 0 && <span className={`count${alert ? " is-hot" : ""}`}>{count}</span>}
    </a>
  );
}

export function Sidebar({ ai, children }: { ai: AIStatus; children: React.ReactNode }) {
  return (
    <aside className="sidebar">
      <div className="logo"><span className="logo-mark"><Icon name="split" size={14} strokeWidth={2.2} /></span>Decision OS</div>
      {children}
      <div className="side-foot">
        <div className="engine">
          <b>{ai.mode === "live" ? "Qualcomm Cloud AI Playground" : "Replay mode"}</b>
          {ai.mode === "live" ? ai.model : "No Qualcomm key configured. Bundled demo meetings only."}
        </div>
      </div>
    </aside>
  );
}

export function SimPill({ today, simulated }: { today: string; simulated: boolean }) {
  if (!simulated) return null;
  return <span className="pill pill-sim" title="Deadline checks run as if today were this date"><Icon name="calendar" size={13} />Simulated date · {fmtDate(today)}</span>;
}

export function SourceSheet({ meetingId, start, end, title, subtitle, onClose }: {
  meetingId: string; start: number; end: number; title: string; subtitle?: string; onClose: () => void;
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
      <div className="scrim" onClick={onClose} />
      <aside className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <div className="sheet-head">
          <div style={{ flex: 1 }}>
            <div className="tiny muted" style={{ fontWeight: 600 }}>Source</div>
            <h2 id="sheet-title" style={{ fontSize: 16, marginTop: 2 }}>{title}</h2>
            {subtitle && <div className="small muted" style={{ marginTop: 2 }}>{subtitle}</div>}
          </div>
          <button ref={closeRef} className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        </div>
        <div className="sheet-body">
          {err && <div className="alert alert-error">{err}</div>}
          {!src && !err && <div className="row muted small"><span className="spinner dark" /> Loading notes…</div>}
          {src && (
            <>
              <div className="row small muted"><Icon name="file" size={14} />{src.topic} · meeting of {fmtDate(src.meeting_date)}</div>
              <div className="source">
                {src.notes.slice(0, start)}
                <mark ref={markRef}>{src.notes.slice(start, end)}</mark>
                {src.notes.slice(end)}
              </div>
              <p className="small muted">The highlighted sentence is the exact text this item was extracted from. Items without a matching sentence are rejected, not shown.</p>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
