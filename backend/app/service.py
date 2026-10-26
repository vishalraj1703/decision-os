"""Application logic shared by the API, the scheduler and tests."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from . import cascade, dates, extract
from .config import Settings
from .db import DB, new_id
from .roster import PEOPLE, Person, find_person

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
        """Rule-based fallback; replaced by the Qualcomm diagnosis in Block 3."""
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
