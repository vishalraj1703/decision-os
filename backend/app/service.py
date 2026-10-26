"""Application logic shared by the API, the scheduler and tests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field

from . import cascade, dates, extract
from .config import Settings
from .db import DB, new_id
from .prompts import callout_messages
from .roster import BY_EMAIL, PEOPLE, Person, find_person

log = logging.getLogger("decisionos.service")

MAX_NOTES = 12000
STATUSES = ("not_started", "in_progress", "blocked", "done")
STATUS_LABEL = {"not_started": "Not Started", "in_progress": "In Progress", "blocked": "Blocked", "done": "Done"}


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def _deadline_text(i: dict) -> str:
    if i["deadline_date"]:
        d = dt.date.fromisoformat(i["deadline_date"])
        txt = dates.fmt(d)
        return txt + (" (needs confirmation)" if i["deadline_status"] == "needs_confirmation" else "")
    if i["deadline_status"] == "after_dependency":
        return "after dependency"
    return "unclear — needs follow-up"


@dataclass
class Service:
    db: DB
    ai: object
    s: Settings
    _callout_busy: set = field(default_factory=set)

    # Feature 1-3: ingest
    def ingest(self, notes: str, meeting_date: dt.date, title: str | None, by: Person) -> dict:
        if by.role != "manager":
            raise AppError("FORBIDDEN", "Only managers can extract meetings.", 403)
        text = notes.replace("\r\n", "\n").strip()
        if not text:
            raise AppError("EMPTY", "Paste some meeting notes first.", 422)
        if len(text) > MAX_NOTES:
            raise AppError("TOO_LONG", f"Notes are {len(text)} characters; the limit is {MAX_NOTES}.", 422)
        try:
            out = extract.run(self.ai, text, meeting_date, self.s.structured_mode)
        except extract.ExtractionFailed as e:
            raise AppError(e.code, e.message, 502 if e.code != "NO_REPLAY" else 422, e.details) from None

        meeting_id = new_id("mtg")
        ids = {it.ref: new_id("itm") for it in out.items}
        rows = []
        for it in out.items:
            person = find_person(it.owner)
            review = "needs_review" if it.missing_info else "ok"
            rows.append({
                "id": ids[it.ref], "kind": it.kind, "ref": it.ref, "text": it.text,
                "owner": person.name if person else it.owner, "owner_user_id": person.id if person else None,
                "team": person.team if person else None,
                "deadline_raw": it.deadline_raw, "deadline_date": it.deadline.date.isoformat() if it.deadline.date else None,
                "deadline_status": it.deadline.status, "deadline_note": it.deadline.note,
                "severity": it.severity, "evidence_quote": it.evidence_quote, "ev_start": it.ev_start, "ev_end": it.ev_end,
                "confidence": it.confidence, "missing_info": it.missing_info,
                "checks": it.checks + ([] if person or not it.owner else [f"'{it.owner}' is not in the team roster."]),
                "review_state": review,
            })
        self._attach_embeddings(rows)
        deps = [(ids[it.ref], ids[d]) for it in out.items for d in it.dependencies if d in ids]
        self.db.save_meeting(
            {"id": meeting_id, "topic": out.topic, "title": title, "meeting_date": meeting_date.isoformat(), "notes": text,
             "created_by": by.id, "model": out.model, "attempts": out.attempts, "latency_ms": out.latency_ms,
             "rejected": out.rejected},
            rows, deps,
        )
        for c in out.contradictions:
            self.db.add_contradiction(
                meeting_id=meeting_id, source="in_meeting", topic=c.topic, current=c.current, previous=c.previous,
                current_evidence=c.current_evidence, previous_evidence=c.previous_evidence,
                explanation="The notes themselves say an earlier decision was different.",
            )
        self.after_ingest(meeting_id)
        log.info("ingested meeting=%s items=%d attempts=%d mode=%s", meeting_id, len(rows), out.attempts, self.ai.mode)
        return {"meeting_id": meeting_id, "topic": out.topic, "items": len(rows), "attempts": out.attempts,
                "latency_ms": out.latency_ms, "model": out.model, "rejected": out.rejected}

    def _attach_embeddings(self, rows: list[dict]) -> None:
        """Decisions get an embedding so later meetings can find conflicting decisions (Feature 4)."""
        decisions = [r for r in rows if r["kind"] == "decision"]
        if not decisions:
            return
        try:
            vecs = self.ai.embed([f"{r['text']}. {r['evidence_quote']}" for r in decisions])
        except Exception as e:  # noqa: BLE001 - conflicts are best effort; extraction must still save
            log.warning("embedding failed: %s", type(e).__name__)
            return
        for r, v in zip(decisions, vecs):
            r["embedding"] = v

    def after_ingest(self, meeting_id: str) -> None:
        """Hooks that run after a meeting is stored (conflicts, cascade)."""
        cascade.recompute(self.db, self.s.timezone)

    # Dashboard state
    def state(self, me: Person) -> dict:
        on, simulated = cascade.today(self.db, self.s.timezone)
        items = self.db.items()
        meetings = {m["id"]: m for m in self.db.meetings()}
        for i in items:
            i["color"] = cascade.color(i)
            i["deadline_text"] = _deadline_text(i)
            m = meetings.get(i["meeting_id"])
            i["meeting"] = {"id": i["meeting_id"], "topic": m["topic"] if m else "", "date": m["meeting_date"] if m else ""}
        live = [i for i in items if i["review_state"] != "discarded"]
        actions = [i for i in live if i["kind"] == "action"]
        by_id = {i["id"]: i for i in items}

        base = {
            "version": self.db.version(),
            "today": on.isoformat(),
            "simulated": simulated,
            "ai": self.ai.status(),
            "me": {"id": me.id, "name": me.name, "role": me.role, "team": me.team},
        }
        if me.role != "manager":
            mine = [i for i in actions if i["owner_user_id"] == me.id]
            for i in mine:
                i["blocked_by"] = [self._brief(by_id[d]) for d in i["depends_on"] if d in by_id]
                i["blocking"] = [self._brief(a) for a in actions if i["id"] in a["depends_on"]]
            notes = self.db.notifications(me.id, manager=False)
            return {**base, "tasks": mine, "notifications": notes, "unread": sum(1 for n in notes if not n["read"])}

        edges = []
        for a in actions:
            for up in a["depends_on"]:
                u = by_id.get(up)
                if u is None:
                    continue
                broken = (u["overdue"] or u["status"] == "blocked") and a["status"] != "done"
                edges.append({"source": up, "target": a["id"], "blocked": broken})
        teams = sorted({a["team"] for a in actions if a["team"]})
        team_rows = []
        rank = {"red": 3, "orange": 2, "grey": 1, "green": 0}
        for t in teams:
            ts = [a for a in actions if a["team"] == t]
            worst = max((a["color"] for a in ts), key=lambda c: rank[c])
            team_rows.append({"team": t, "color": worst, "tasks": len(ts),
                              "label": {"red": "blocked", "orange": "attention", "grey": "waiting", "green": "healthy"}[worst]})
        notes = self.db.notifications(None, manager=True)
        return {
            **base,
            "stats": {
                "teams_in_scope": len(teams),
                "blocked_handoffs": sum(1 for e in edges if e["blocked"]),
                "unassigned_actions": sum(1 for a in actions if a["missing_info"]),
            },
            "callout": self.callout(actions, edges, by_id),
            "graph": {"nodes": actions, "edges": edges},
            "actions": actions,
            "decisions": [i for i in live if i["kind"] == "decision"],
            "risks": [i for i in live if i["kind"] == "risk"],
            "needs_review": [i for i in live if i["review_state"] in ("needs_review", "follow_up")],
            "conflicts": self.db.contradictions(),
            "teams": team_rows,
            "meetings": list(meetings.values()),
            "notifications": notes,
            "unread": sum(1 for n in notes if not n["read"]),
            "emails": self.db.emails(10),
        }

    @staticmethod
    def _brief(i: dict) -> dict:
        return {"id": i["id"], "text": i["text"], "owner": i["owner"], "status": i["status"],
                "overdue": i["overdue"], "deadline_date": i["deadline_date"]}

    def callout(self, actions: list[dict], edges: list[dict], by_id: dict) -> dict:
        """Spec 6.2: the model's one-sentence diagnosis of the most critical blocker.

        Generated in the background and cached per situation, so polling never waits on
        Qualcomm. Until it arrives (or if the AI is unavailable) a rule-based sentence shows.
        """
        rule = self._rule_callout(actions, edges, by_id)
        if not actions or getattr(self.ai, "mode", "") != "live":
            return rule
        snapshot = {
            "today": cascade.today(self.db, self.s.timezone)[0].isoformat(),
            "tasks": [{"task": a["text"], "owner": a["owner"] or "UNKNOWN", "team": a["team"],
                       "deadline": a["deadline_date"] or a["deadline_raw"], "status": a["status"],
                       "overdue": a["overdue"], "at_risk": a["at_risk"],
                       "waits_on": [by_id[d]["text"] for d in a["depends_on"] if d in by_id]} for a in actions],
        }
        sig = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:16]
        cached = self.db.get_meta(f"callout:{sig}")
        if cached:
            return {**json.loads(cached), "severity": rule["severity"], "source": "ai"}
        if sig not in self._callout_busy:
            self._callout_busy.add(sig)
            threading.Thread(target=self._fetch_callout, args=(sig, snapshot), daemon=True).start()
        return rule

    def _fetch_callout(self, sig: str, snapshot: dict) -> None:
        try:
            r = self.ai.chat(callout_messages(snapshot), max_tokens=80, temperature=0.2)
            text = (r.text or "").strip().strip('"').splitlines()[0][:220] if r.text else ""
            if text:
                self.db.set_meta(f"callout:{sig}", json.dumps({"text": text}))
                self.db.bump()
        except Exception as e:  # noqa: BLE001 - the rule-based callout stays
            log.warning("callout generation failed: %s", type(e).__name__)
        finally:
            self._callout_busy.discard(sig)

    # Employee execution layer (spec 7)
    def update_status(self, me: Person, item_id: str, status: str, reason: str | None) -> dict:
        if status not in STATUSES:
            raise AppError("INVALID", "Status must be Not Started, In Progress, Blocked or Done.", 422)
        it = self.db.item(item_id)
        if it is None or it["kind"] != "action":
            raise AppError("NOT_FOUND", "Task not found.", 404)
        if me.role != "manager" and it["owner_user_id"] != me.id:
            raise AppError("FORBIDDEN", "You can only update your own tasks.", 403)
        if it["review_state"] == "discarded":
            raise AppError("INVALID", "This task was discarded.", 422)
        reason = (reason or "").strip()[:200] or None
        if it["status"] == status and (status != "blocked" or reason == it["blocked_reason"]):
            return it
        self.db.update_item(item_id, status=status, blocked_reason=reason if status == "blocked" else None)
        actions = [a for a in self.db.items("WHERE kind='action'") if a["review_state"] != "discarded"]
        by_id = {a["id"]: a for a in actions}
        downstream = [a for a in actions if item_id in a["depends_on"]]
        who = it["owner"] or "Someone"

        if status == "blocked":
            why = f": {reason}" if reason else ""
            down = ", ".join(f"{d['owner'] or 'UNKNOWN'}'s {d['text']}" for d in downstream)
            self.db.notify("managers", "blocked", f"{who} marked '{it['text']}' blocked{why}." + (f" This blocks {down}." if down else ""),
                           link=f"/manager#row-{item_id}", dedupe_key=f"blocked:{item_id}:{reason}:{self.db.version()}")
            for d in downstream:
                if d["owner_user_id"]:
                    self.db.notify("user", "upstream_blocked", f"{who} has not finished '{it['text']}' and marked it blocked. Your task '{d['text']}' is blocked.",
                                   link=f"/me#{d['id']}", user_id=d["owner_user_id"], dedupe_key=f"upblocked:{item_id}:{d['id']}:{self.db.version()}")
        elif status == "done":
            self.db.notify("managers", "done", f"{who} completed '{it['text']}'.", link=f"/manager#row-{item_id}",
                           dedupe_key=f"done:{item_id}:{self.db.version()}")
            for d in downstream:
                ready = all(by_id[u]["status"] == "done" for u in d["depends_on"] if u in by_id)
                if ready and d["owner_user_id"]:
                    self.db.notify("user", "unblocked", f"{who}'s '{it['text']}' is complete. You can start '{d['text']}'.",
                                   link=f"/me#{d['id']}", user_id=d["owner_user_id"], dedupe_key=f"unblocked:{item_id}:{d['id']}")
                    self.on_dependency_complete(it, d)
        cascade.recompute(self.db, self.s.timezone)
        return self.db.item(item_id) or {}

    def on_dependency_complete(self, upstream: dict, downstream: dict) -> None:
        """Hook for email trigger 3 (Block 7)."""

    def read_notifications(self, me: Person) -> None:
        self.db.mark_read(me.id, me.role == "manager")

    # Needs Review queue (spec 5.4)
    def resolve_item(self, me: Person, item_id: str, action: str, value: str | None) -> dict:
        if me.role != "manager":
            raise AppError("FORBIDDEN", "Only managers resolve review items.", 403)
        it = self.db.item(item_id)
        if it is None:
            raise AppError("NOT_FOUND", "Item not found.", 404)
        missing = list(it["missing_info"])
        checks = list(it["checks"])
        fields: dict = {}
        if action == "assign_owner":
            p = BY_EMAIL.get((value or "").strip().lower()) or find_person(value)
            if p is None:
                raise AppError("INVALID", "Pick someone from the team roster.", 422)
            fields.update(owner=p.name, owner_user_id=p.id, team=p.team)
            missing = [m for m in missing if m != "owner"]
            checks.append(f"Owner set to {p.name} by {me.name}.")
        elif action == "set_deadline":
            try:
                d = dt.date.fromisoformat(value or "")
            except ValueError:
                raise AppError("INVALID", "Deadline must be a date (YYYY-MM-DD).", 422) from None
            fields.update(deadline_date=d.isoformat(), deadline_status="exact", deadline_note=f"Set by {me.name}.")
            missing = [m for m in missing if m not in ("deadline", "deadline_confirmation")]
            checks.append(f"Deadline set to {d.isoformat()} by {me.name}.")
        elif action == "confirm_deadline":
            if it["deadline_status"] != "needs_confirmation":
                raise AppError("INVALID", "This deadline does not need confirmation.", 422)
            fields.update(deadline_status="exact", deadline_note=f"Confirmed by {me.name}.")
            missing = [m for m in missing if m != "deadline_confirmation"]
        elif action == "follow_up":
            fields["review_state"] = "follow_up"
            checks.append(f"Marked for a follow-up meeting by {me.name}.")
        elif action == "discard":
            fields["review_state"] = "discarded"
            checks.append(f"Discarded as noise by {me.name}.")
        else:
            raise AppError("INVALID", f"Unknown action '{action}'.", 422)
        fields["missing_info"] = missing
        fields["checks"] = checks
        if "review_state" not in fields:
            fields["review_state"] = "needs_review" if missing else "ok"
        self.db.update_item(item_id, **fields)
        if action == "assign_owner" and it["kind"] == "action":
            self.db.notify("user", "assigned", f"You were assigned: {it['text']}.", link=f"/me#{item_id}",
                           user_id=fields["owner_user_id"], dedupe_key=f"assigned:{item_id}:{fields['owner_user_id']}")
        cascade.recompute(self.db, self.s.timezone)
        return self.db.item(item_id) or {}

    def _rule_callout(self, actions: list[dict], edges: list[dict], by_id: dict) -> dict:
        blocked = [a for a in actions if a["status"] == "blocked" or a["overdue"]]
        if blocked:
            a = blocked[0]
            down = [by_id[e["target"]]["text"] for e in edges if e["source"] == a["id"]]
            why = "is blocked" if a["status"] == "blocked" else "is overdue"
            tail = f" This blocks: {', '.join(down)}." if down else ""
            return {"text": f"{a['text']} ({a['owner'] or 'owner unknown'}) {why}.{tail}", "severity": "red", "source": "rule"}
        review = [a for a in actions if a["missing_info"]]
        if review:
            return {"text": f"{len(review)} action{'s' if len(review) != 1 else ''} need review: owner or deadline not stated in the notes.",
                    "severity": "amber", "source": "rule"}
        if actions:
            return {"text": "No blockers. All handoffs are on track.", "severity": "grey", "source": "rule"}
        return {"text": "Paste meeting notes to build the decision graph.", "severity": "grey", "source": "rule"}

    def meeting_source(self, meeting_id: str) -> dict:
        m = self.db.meeting(meeting_id)
        if m is None:
            raise AppError("NOT_FOUND", "Meeting not found.", 404)
        return {"id": m["id"], "topic": m["topic"], "meeting_date": m["meeting_date"], "notes": m["notes"],
                "rejected": m["rejected"], "model": m["model"], "attempts": m["attempts"]}

    @staticmethod
    def people() -> list[dict]:
        return [{"id": p.id, "name": p.name, "email": p.email, "team": p.team, "role": p.role} for p in PEOPLE]
