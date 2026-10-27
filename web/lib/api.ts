"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Color = "grey" | "orange" | "red" | "green";
export type Status = "not_started" | "in_progress" | "blocked" | "done";

export interface Item {
  id: string; meeting_id: string; kind: "action" | "decision" | "risk"; ref: string; text: string;
  owner: string | null; owner_user_id: string | null; team: string | null;
  deadline_raw: string | null; deadline_date: string | null; deadline_status: string; deadline_note: string | null; deadline_text: string;
  severity: string | null; evidence_quote: string; ev_start: number; ev_end: number; confidence: number;
  missing_info: string[]; checks: string[]; status: Status; blocked_reason: string | null;
  review_state: "ok" | "needs_review" | "follow_up" | "discarded" | "superseded";
  overdue: boolean; at_risk: boolean; depends_on: string[]; color: Color;
  verification: Verification | null;
  meeting: { id: string; topic: string; date: string };
  blocked_by?: Brief[]; blocking?: Brief[];
}
/** Trust Receipt: quote found in code, meaning judged by the Verifier (null = not checked). */
export interface Verification { quote_found: boolean; supported: boolean | null; owner_ok: boolean | null; deadline_ok: boolean | null; by: string | null; note: string | null }
export interface ReplayRow {
  kind: "action" | "decision" | "risk"; text: string; owner: string; deadline: string; evidence: string;
  outcome: "kept" | "corrected" | "removed"; final: { owner: string; deadline: string } | null;
  reasons: { by: "code" | "verifier"; text: string }[];
}
export interface VerifyInfo { status?: "ok" | "failed" | "skipped"; model?: string | null; latency_ms?: number; attempts?: number; removed?: number; corrected?: number }
export interface AICall { id: string; meeting_id: string | null; purpose: string; mode: string; model: string | null; latency_ms: number | null; ok: boolean; verdict: string | null; created_at: string }
export interface Brief { id: string; text: string; owner: string | null; status: Status; overdue: boolean; deadline_date: string | null }
export interface Conflict {
  id: string; meeting_id: string; previous_meeting_id: string | null; source: "in_meeting" | "cross_meeting" | "disagreement";
  topic: string; current: string; previous: string; current_evidence: string; previous_evidence: string;
  explanation: string | null; status: "open" | "confirmed_current" | "reverted" | "follow_up"; resolved_by: string | null; created_at: string;
}
export interface Notification { id: string; kind: string; text: string; link: string | null; read: number; created_at: string }
export interface Meeting {
  id: string; topic: string; title: string | null; meeting_date: string; model: string; attempts: number; latency_ms: number;
  rejected: { kind: string; text: string; reason: string; by?: "code" | "verifier" }[];
  replay: ReplayRow[]; verify: VerifyInfo; redactions: Record<string, number>;
}
export interface Email { id: string; trigger: string; to_email: string; delivered_to: string | null; subject: string; status: string; error: string | null; created_at: string }
export interface AIStatus { mode: "live" | "replay" | "test"; model: string; reason?: string; last_error?: string | null }

export interface BaseState {
  changed: true; version: number; today: string; simulated: boolean; ai: AIStatus;
  me: { id: string; name: string; role: "manager" | "employee"; team: string };
  notifications: Notification[]; unread: number;
}
export interface ManagerState extends BaseState {
  stats: { teams_in_scope: number; blocked_handoffs: number; unassigned_actions: number };
  callout: { text: string; severity: "red" | "amber" | "grey"; source: "ai" | "rule" };
  graph: { nodes: Item[]; edges: { source: string; target: string; blocked: boolean }[] };
  actions: Item[]; decisions: Item[]; risks: Item[]; needs_review: Item[]; conflicts: Conflict[];
  teams: { team: string; color: Color; label: string; tasks: number }[];
  meetings: Meeting[]; emails: Email[]; ai_calls: AICall[];
}
export interface EmployeeState extends BaseState { tasks: Item[] }

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`/api/backend/${path}`, {
      method, headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store",
    });
  } catch {
    throw new ApiError("NETWORK", "Cannot reach the server.", 0);
  }
  const text = await r.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* not JSON */ }
  if (!r.ok) {
    const e = (data ?? {}) as { code?: string; message?: string };
    throw new ApiError(e.code ?? `HTTP_${r.status}`, e.message ?? "Request failed.", r.status);
  }
  return data as T;
}

/** Poll /state every second; only re-render when the server version changes. */
export function useLiveState<T extends BaseState>(intervalMs = 1000) {
  const [state, setState] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const version = useRef<number | null>(null);

  const refresh = useCallback(async (force = false) => {
    try {
      const q = !force && version.current !== null ? `?since=${version.current}` : "";
      const r = await api<T | { changed: false; version: number }>(`state${q}`);
      if (r.changed) {
        version.current = r.version;
        setState(r as T);
      }
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh(true);
    const t = window.setInterval(() => { if (!document.hidden) refresh(); }, intervalMs);
    return () => window.clearInterval(t);
  }, [refresh, intervalMs]);

  return { state, error, refresh: () => refresh(true) };
}

export const STATUS_LABEL: Record<Status, string> = { not_started: "Not Started", in_progress: "In Progress", blocked: "Blocked", done: "Done" };

export function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}
