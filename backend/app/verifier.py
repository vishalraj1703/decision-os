"""Pass 2: the Verifier. A second Qualcomm call re-reads the notes and judges each claim
that survived the code checks: is it really stated, and are its owner and deadline?

The Verifier can only remove a claim or downgrade a field to UNKNOWN; it never adds or
rewrites anything. If it fails twice, every item is kept and marked "not verified".
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from . import dates
from .prompts import verify_messages
from .qualcomm import QualcommError
from .schema import UNKNOWN, AIVerification

log = logging.getLogger("decisionos.verifier")


@dataclass
class VerifyOutcome:
    status: str  # ok | failed | skipped
    model: str | None = None
    latency_ms: int = 0
    attempts: int = 0
    error: str | None = None
    removed: list[tuple[object, str]] = field(default_factory=list)  # (CheckedItem, reason)
    corrected: int = 0

    def summary(self) -> dict:
        return {"status": self.status, "model": self.model, "latency_ms": self.latency_ms, "attempts": self.attempts,
                "error": self.error, "removed": len(self.removed), "corrected": self.corrected}


def _claims(items: list) -> list[dict]:
    return [{"id": i.ref, "kind": i.kind, "text": i.text, "owner": i.owner or UNKNOWN, "deadline": i.deadline_raw,
             "evidence": i.evidence_quote} for i in items]


def _parse_verdicts(text: str) -> AIVerification:
    from .extract import _parse  # the same lenient JSON reader the extractor uses

    try:
        data = _parse(text)
    except ValueError:
        # Some models answer with the bare list.
        body = (text or "").strip()
        a, b = body.find("["), body.rfind("]")
        if a < 0 or b <= a:
            raise
        data = {"verdicts": json.loads(body[a : b + 1])}
    if "verdicts" not in data:
        data = {"verdicts": next((v for v in data.values() if isinstance(v, list)), [])}
    return AIVerification.model_validate(data)


def mark_unverified(items: list, why: str) -> None:
    for i in items:
        i.verification = {"quote_found": True, "supported": None, "owner_ok": None, "deadline_ok": None, "by": None, "note": why}


def verify(ai, notes: str, items: list, meeting_date: dt.date) -> VerifyOutcome:
    """Judge `items` in place. Removed items are returned, not deleted from the list."""
    if not items:
        return VerifyOutcome(status="skipped")
    messages = verify_messages(notes, _claims(items))
    out = VerifyOutcome(status="failed", model=getattr(ai, "model", None))
    result: AIVerification | None = None
    while out.attempts < 2 and result is None:
        out.attempts += 1
        try:
            r = ai.chat(messages, temperature=0.0)
        except QualcommError as e:
            out.error = e.code
            if not e.retryable:
                break
            continue
        out.latency_ms += r.latency_ms
        out.model = r.model
        try:
            result = _parse_verdicts(r.text)
        except (ValueError, ValidationError) as e:
            out.error = "INVALID_VERIFIER_REPLY"
            log.info("verifier attempt %d unusable: %s", out.attempts, str(e)[:200])
            annotate(ai, "unusable reply")
    if result is None:
        mark_unverified(items, "The Verifier did not answer, so this item was not checked for meaning.")
        log.warning("verifier failed: %s", out.error)
        return out

    out.status, out.error = "ok", None
    by_id = {v.id: v for v in result.verdicts}
    for i in items:
        v = by_id.get(i.ref)
        if v is None:
            i.verification = {"quote_found": True, "supported": None, "owner_ok": None, "deadline_ok": None,
                              "by": out.model, "note": "The Verifier skipped this item."}
            continue
        if not v.supported:
            out.removed.append((i, v.reason or "The notes do not state this as agreed."))
            continue
        why = f" {v.reason}" if v.reason else ""
        changed = False
        if not v.owner_stated and i.owner:
            i.checks.append(f"Verifier: '{i.owner}' is not stated as the owner, so the owner is UNKNOWN.{why}")
            i.owner = None
            if i.kind in ("action", "risk") and "owner" not in i.missing_info:
                i.missing_info.append("owner")
            changed = True
        if not v.deadline_stated and i.deadline_raw != UNKNOWN and i.status != "done":
            i.checks.append(f"Verifier: the deadline '{i.deadline_raw}' is not stated for this item, so it is UNKNOWN.{why}")
            i.deadline_raw = UNKNOWN
            i.deadline = dates.normalize(UNKNOWN, meeting_date)
            i.missing_info = [m for m in i.missing_info if m != "deadline_confirmation"]
            if i.kind == "action" and "deadline" not in i.missing_info:
                i.missing_info.append("deadline")
            changed = True
        out.corrected += changed
        i.verification = {"quote_found": True, "supported": True, "owner_ok": v.owner_stated, "deadline_ok": v.deadline_stated,
                          "by": out.model, "note": v.reason or None}
    annotate(ai, f"{len(items) - len(out.removed)} supported, {len(out.removed)} removed, {out.corrected} corrected")
    return out


def annotate(ai, verdict: str) -> None:
    """Attach a verdict to the audit-log row of the call just made (when the AI is audited)."""
    f = getattr(ai, "annotate", None)
    if f:
        f(verdict)
