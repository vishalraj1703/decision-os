"""SQLite storage. Every write bumps a global version so dashboards can poll cheaply."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY, topic TEXT NOT NULL, title TEXT, meeting_date TEXT NOT NULL, notes TEXT NOT NULL,
    created_by TEXT, model TEXT, attempts INTEGER, latency_ms INTEGER, rejected_json TEXT, created_at TEXT NOT NULL,
    replay_json TEXT, verify_json TEXT, redactions_json TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, ref TEXT NOT NULL, text TEXT NOT NULL,
    owner TEXT, owner_user_id TEXT, team TEXT,
    deadline_raw TEXT, deadline_date TEXT, deadline_status TEXT, deadline_note TEXT,
    severity TEXT, evidence_quote TEXT NOT NULL, ev_start INTEGER, ev_end INTEGER, confidence REAL,
    missing_info TEXT NOT NULL DEFAULT '[]', checks TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'not_started', blocked_reason TEXT,
    review_state TEXT NOT NULL DEFAULT 'ok', overdue INTEGER NOT NULL DEFAULT 0, at_risk INTEGER NOT NULL DEFAULT 0,
    embedding TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, verification TEXT, slack_days INTEGER, evidence_hash TEXT
);
CREATE TABLE IF NOT EXISTS dependencies (
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    depends_on TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, depends_on)
);
CREATE TABLE IF NOT EXISTS contradictions (
    id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    previous_meeting_id TEXT, current_item_id TEXT, previous_item_id TEXT, source TEXT NOT NULL,
    topic TEXT NOT NULL, current TEXT NOT NULL, previous TEXT NOT NULL,
    current_evidence TEXT NOT NULL, previous_evidence TEXT NOT NULL, explanation TEXT,
    status TEXT NOT NULL DEFAULT 'open', resolved_by TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY, audience TEXT NOT NULL, user_id TEXT, kind TEXT NOT NULL, text TEXT NOT NULL,
    link TEXT, dedupe_key TEXT UNIQUE, read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY, trigger TEXT NOT NULL, item_id TEXT, to_email TEXT NOT NULL, delivered_to TEXT,
    subject TEXT NOT NULL, status TEXT NOT NULL, provider_id TEXT, error TEXT, dedupe_key TEXT UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clarifications (
    id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE, flag TEXT NOT NULL,
    to_user_id TEXT NOT NULL, question TEXT NOT NULL, sent_by TEXT, email_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_calls (
    id TEXT PRIMARY KEY, meeting_id TEXT, purpose TEXT NOT NULL, mode TEXT, model TEXT, latency_ms INTEGER,
    ok INTEGER NOT NULL, verdict TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, created_at TEXT NOT NULL
);
"""

# Columns added after the first deployment; older databases get them on start-up.
MIGRATIONS = [
    ("meetings", "replay_json", "TEXT"), ("meetings", "verify_json", "TEXT"), ("meetings", "redactions_json", "TEXT"),
    ("items", "verification", "TEXT"), ("items", "slack_days", "INTEGER"), ("items", "evidence_hash", "TEXT"),
]


def evidence_hash(quote: str) -> str:
    """Fingerprint of an evidence quote: shows later that the quote was not altered."""
    return hashlib.sha256(" ".join(quote.split()).encode("utf-8")).hexdigest()[:16]


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self._mem = None
        if self.path == ":memory:":
            self._mem = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.tx() as c:
            c.executescript(SCHEMA)
            for table, col, kind in MIGRATIONS:
                if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
            c.execute("INSERT OR IGNORE INTO meta VALUES ('version', '1')")

    @contextmanager
    def tx(self, bump: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._mem or sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                if bump:
                    conn.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key='version'")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                if self._mem is None:
                    conn.close()

    def version(self) -> int:
        with self.tx() as c:
            return int(c.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])

    def bump(self) -> None:
        with self.tx(bump=True):
            pass

    def get_meta(self, key: str) -> str | None:
        with self.tx() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r[0] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # Reads
    def items(self, where: str = "", args: tuple = ()) -> list[dict]:
        with self.tx() as c:
            rows = c.execute(f"SELECT * FROM items {where} ORDER BY created_at, ref", args).fetchall()
            deps = c.execute("SELECT item_id, depends_on FROM dependencies").fetchall()
        dep_map: dict[str, list[str]] = {}
        for d in deps:
            dep_map.setdefault(d["item_id"], []).append(d["depends_on"])
        out = []
        for r in rows:
            d = dict(r)
            d["missing_info"] = json.loads(d["missing_info"] or "[]")
            d["checks"] = json.loads(d["checks"] or "[]")
            d["verification"] = json.loads(d["verification"]) if d.get("verification") else None
            d["embedding"] = None if d["embedding"] is None else "stored"
            d["overdue"] = bool(d["overdue"])
            d["at_risk"] = bool(d["at_risk"])
            d["depends_on"] = dep_map.get(d["id"], [])
            out.append(d)
        return out

    def item(self, item_id: str) -> dict | None:
        rows = self.items("WHERE id=?", (item_id,))
        return rows[0] if rows else None

    def item_embeddings(self, kind: str, exclude_meeting: str) -> list[tuple[dict, list[float]]]:
        with self.tx() as c:
            rows = c.execute(
                "SELECT i.*, m.meeting_date AS m_date, m.topic AS m_topic FROM items i JOIN meetings m ON m.id=i.meeting_id "
                "WHERE i.kind=? AND i.meeting_id<>? AND i.embedding IS NOT NULL AND i.review_state<>'discarded'",
                (kind, exclude_meeting),
            ).fetchall()
        return [(dict(r), json.loads(r["embedding"])) for r in rows]

    def item_embeddings_for_meeting(self, meeting_id: str, kind: str) -> list[tuple[dict, list[float]]]:
        with self.tx() as c:
            rows = c.execute("SELECT * FROM items WHERE meeting_id=? AND kind=? AND embedding IS NOT NULL", (meeting_id, kind)).fetchall()
        return [(dict(r), json.loads(r["embedding"])) for r in rows]

    def drop_in_meeting_duplicate(self, meeting_id: str, current_evidence: str) -> None:
        with self.tx(bump=True) as c:
            c.execute("DELETE FROM contradictions WHERE meeting_id=? AND source='in_meeting' AND current_evidence=?",
                      (meeting_id, current_evidence))

    def meetings(self) -> list[dict]:
        with self.tx() as c:
            rows = c.execute("SELECT id, topic, title, meeting_date, created_at, model, attempts, latency_ms, rejected_json, "
                             "replay_json, verify_json, redactions_json FROM meetings ORDER BY meeting_date, created_at").fetchall()
        return [_meeting_row(r) for r in rows]

    def meeting(self, meeting_id: str) -> dict | None:
        with self.tx() as c:
            r = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        return None if r is None else _meeting_row(r)

    def contradictions(self) -> list[dict]:
        with self.tx() as c:
            return [dict(r) for r in c.execute("SELECT * FROM contradictions ORDER BY created_at DESC").fetchall()]

    def notifications(self, user_id: str | None, manager: bool, limit: int = 30) -> list[dict]:
        with self.tx() as c:
            if manager:
                rows = c.execute("SELECT * FROM notifications WHERE audience='managers' ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
            else:
                rows = c.execute("SELECT * FROM notifications WHERE audience='user' AND user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                 (user_id, limit))
            return [dict(r) for r in rows.fetchall()]

    def clarifications(self) -> list[dict]:
        with self.tx() as c:
            return [dict(r) for r in c.execute("SELECT * FROM clarifications ORDER BY created_at").fetchall()]

    def add_clarification(self, **f: Any) -> str:
        cid = new_id("clq")
        with self.tx(bump=True) as c:
            c.execute("INSERT INTO clarifications (id, item_id, flag, to_user_id, question, sent_by, email_id, created_at) "
                      "VALUES (?,?,?,?,?,?,?,?)",
                      (cid, f["item_id"], f["flag"], f["to_user_id"], f["question"], f.get("sent_by"), f.get("email_id"),
                       now().isoformat()))
        return cid

    def ai_calls(self, limit: int = 20) -> list[dict]:
        with self.tx() as c:
            rows = c.execute("SELECT * FROM ai_calls ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "ok": bool(r["ok"])} for r in rows]

    def emails(self, limit: int = 30) -> list[dict]:
        with self.tx() as c:
            return [dict(r) for r in c.execute("SELECT * FROM emails ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()]

    # Writes
    def log_ai_call(self, **f: Any) -> str:
        """Audit log row. Holds no notes or replies, only what the call was and how it went."""
        cid = new_id("aic")
        with self.tx() as c:
            c.execute(
                "INSERT INTO ai_calls (id, meeting_id, purpose, mode, model, latency_ms, ok, verdict, prompt_tokens, completion_tokens, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (cid, f.get("meeting_id"), f["purpose"], f.get("mode"), f.get("model"), f.get("latency_ms"), int(f["ok"]),
                 f.get("verdict"), f.get("prompt_tokens"), f.get("completion_tokens"), now().isoformat()),
            )
        return cid

    def annotate_ai_call(self, cid: str, verdict: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE ai_calls SET verdict=? WHERE id=?", (verdict[:200], cid))

    def update_item(self, item_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = now().isoformat()
        for k in ("missing_info", "checks"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.tx(bump=True) as c:
            c.execute(f"UPDATE items SET {cols} WHERE id=?", (*fields.values(), item_id))

    def set_flags(self, flags: dict[str, tuple[bool, bool]]) -> None:
        """Bulk-update overdue/at_risk; bumps the version only if something changed."""
        with self.tx() as c:
            changed = False
            for item_id, (overdue, at_risk) in flags.items():
                cur = c.execute("UPDATE items SET overdue=?, at_risk=? WHERE id=? AND (overdue<>? OR at_risk<>?)",
                                (int(overdue), int(at_risk), item_id, int(overdue), int(at_risk)))
                changed = changed or cur.rowcount > 0
            if changed:
                c.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key='version'")

    def notify(self, audience: str, kind: str, text: str, link: str | None = None, user_id: str | None = None,
               dedupe_key: str | None = None) -> bool:
        with self.tx(bump=True) as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO notifications (id, audience, user_id, kind, text, link, dedupe_key, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (new_id("ntf"), audience, user_id, kind, text, link, dedupe_key, now().isoformat()),
            )
            return cur.rowcount > 0

    def mark_read(self, user_id: str | None, manager: bool) -> None:
        with self.tx(bump=True) as c:
            if manager:
                c.execute("UPDATE notifications SET read=1 WHERE audience='managers'")
            else:
                c.execute("UPDATE notifications SET read=1 WHERE audience='user' AND user_id=?", (user_id,))

    def email_claim(self, dedupe_key: str, trigger: str, item_id: str | None, to_email: str, subject: str) -> str | None:
        """Reserve an email slot; returns the email id, or None if this trigger already fired."""
        with self.tx() as c:
            eid = new_id("eml")
            cur = c.execute(
                "INSERT OR IGNORE INTO emails (id, trigger, item_id, to_email, subject, status, dedupe_key, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (eid, trigger, item_id, to_email, subject, "pending", dedupe_key, now().isoformat()),
            )
            return eid if cur.rowcount else None

    def email_done(self, eid: str, status: str, delivered_to: str | None, provider_id: str | None, error: str | None) -> None:
        with self.tx(bump=True) as c:
            c.execute("UPDATE emails SET status=?, delivered_to=?, provider_id=?, error=? WHERE id=?",
                      (status, delivered_to, provider_id, error, eid))

    def email_release(self, dedupe_key: str) -> None:
        """Forget a failed email so the trigger can fire again on the next check."""
        with self.tx() as c:
            c.execute("UPDATE emails SET dedupe_key=NULL WHERE dedupe_key=? AND status IN ('failed','skipped')", (dedupe_key,))

    def resolve_contradiction(self, cid: str, status: str, by: str) -> bool:
        with self.tx(bump=True) as c:
            return c.execute("UPDATE contradictions SET status=?, resolved_by=? WHERE id=?", (status, by, cid)).rowcount > 0

    def add_contradiction(self, **f: Any) -> str:
        cid = new_id("cfl")
        with self.tx(bump=True) as c:
            c.execute(
                "INSERT INTO contradictions (id, meeting_id, previous_meeting_id, current_item_id, previous_item_id, source, topic, "
                "current, previous, current_evidence, previous_evidence, explanation, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'open',?)",
                (cid, f["meeting_id"], f.get("previous_meeting_id"), f.get("current_item_id"), f.get("previous_item_id"),
                 f["source"], f["topic"], f["current"], f["previous"], f["current_evidence"], f["previous_evidence"],
                 f.get("explanation"), now().isoformat()),
            )
        return cid

    def save_meeting(self, meeting: dict, items: list[dict], deps: list[tuple[str, str]]) -> None:
        ts = now().isoformat()
        with self.tx(bump=True) as c:
            c.execute(
                "INSERT INTO meetings (id, topic, title, meeting_date, notes, created_by, model, attempts, latency_ms, rejected_json, "
                "replay_json, verify_json, redactions_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (meeting["id"], meeting["topic"], meeting.get("title"), meeting["meeting_date"], meeting["notes"],
                 meeting.get("created_by"), meeting.get("model"), meeting.get("attempts"), meeting.get("latency_ms"),
                 json.dumps(meeting.get("rejected", [])), json.dumps(meeting.get("replay", [])),
                 json.dumps(meeting.get("verify", {})), json.dumps(meeting.get("redactions", {})), ts),
            )
            for it in items:
                c.execute(
                    "INSERT INTO items (id, meeting_id, kind, ref, text, owner, owner_user_id, team, deadline_raw, deadline_date, "
                    "deadline_status, deadline_note, severity, evidence_quote, ev_start, ev_end, confidence, missing_info, checks, "
                    "status, review_state, embedding, verification, evidence_hash, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (it["id"], meeting["id"], it["kind"], it["ref"], it["text"], it.get("owner"), it.get("owner_user_id"),
                     it.get("team"), it.get("deadline_raw"), it.get("deadline_date"), it.get("deadline_status"), it.get("deadline_note"),
                     it.get("severity"), it["evidence_quote"], it.get("ev_start"), it.get("ev_end"), it.get("confidence"),
                     json.dumps(it.get("missing_info", [])), json.dumps(it.get("checks", [])), it.get("status", "not_started"),
                     it.get("review_state", "ok"), json.dumps(it["embedding"]) if it.get("embedding") else None,
                     json.dumps(it["verification"]) if it.get("verification") else None, evidence_hash(it["evidence_quote"]), ts, ts),
                )
            for a, b in deps:
                c.execute("INSERT OR IGNORE INTO dependencies VALUES (?,?)", (a, b))

    def purge_meeting(self, meeting_id: str) -> dict | None:
        """Delete a meeting and everything derived from it: items, conflicts on either side,
        questions, notifications and emails about its items. The AI call log keeps its rows
        (they hold no text)."""
        with self.tx(bump=True) as c:
            if c.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone() is None:
                return None
            items = [r[0] for r in c.execute("SELECT id FROM items WHERE meeting_id=?", (meeting_id,))]
            marks = ",".join("?" * len(items)) or "''"
            conflicts = [r[0] for r in c.execute(
                f"SELECT id FROM contradictions WHERE meeting_id=? OR previous_meeting_id=? "
                f"OR current_item_id IN ({marks}) OR previous_item_id IN ({marks})", (meeting_id, meeting_id, *items, *items))]
            notes = 0
            for ref in items + conflicts:
                notes += c.execute("DELETE FROM notifications WHERE link LIKE ?", (f"%{ref}%",)).rowcount
            emails = c.execute(f"DELETE FROM emails WHERE item_id IN ({marks})", items).rowcount if items else 0
            if conflicts:
                c.execute(f"DELETE FROM contradictions WHERE id IN ({','.join('?' * len(conflicts))})", conflicts)
            c.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
        return {"items": len(items), "conflicts": len(conflicts), "notifications": notes, "emails": emails}

    def add_dependency(self, item_id: str, depends_on: str) -> None:
        with self.tx(bump=True) as c:
            c.execute("INSERT OR IGNORE INTO dependencies VALUES (?,?)", (item_id, depends_on))

    def reset(self) -> None:
        with self.tx(bump=True) as c:
            for t in ("emails", "notifications", "clarifications", "contradictions", "dependencies", "items", "meetings"):
                c.execute(f"DELETE FROM {t}")


def _meeting_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["rejected"] = json.loads(d.pop("rejected_json") or "[]")
    d["replay"] = json.loads(d.pop("replay_json", None) or "[]")
    d["verify"] = json.loads(d.pop("verify_json", None) or "{}")
    d["redactions"] = json.loads(d.pop("redactions_json", None) or "{}")
    return d
