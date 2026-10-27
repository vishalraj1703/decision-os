"""Feature 4: decision conflicts across meetings, using three Qualcomm models.

1. Embeddings (BAAI/bge-large-en-v1.5): each decision is stored as a vector, so a new
   decision finds earlier ones with the same meaning even when worded differently
   ("Cloud provider" vs "Hosting choice"), instead of relying on an exact topic string.
2. Reranker (optional, QUALCOMM_RERANKER_MODEL; not available on every account): orders candidates.
   Without it, embedding similarity order is used.
3. Chat (Llama-3.1-8B): confirms whether the pair is a real reversal, not just related.

Only pairs the chat model confirms become conflict cards, with both evidence quotes.
"""

from __future__ import annotations

import json
import logging
import math

from .db import DB
from .prompts import conflict_messages
from .schema import AIConflictCheck

log = logging.getLogger("decisionos.conflicts")

MIN_SIMILARITY = 0.35  # loose on purpose: the chat model makes the final call
CANDIDATES = 5
CONFIRM_TOP = 2


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _parse(text: str) -> AIConflictCheck | None:
    body = (text or "").strip()
    a, b = body.find("{"), body.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return AIConflictCheck.model_validate(json.loads(body[a : b + 1]))
    except (ValueError, TypeError):
        return None


def detect(db: DB, ai, meeting_id: str) -> list[str]:
    """Compare this meeting's decisions with earlier meetings; store confirmed conflicts."""
    meeting = db.meeting(meeting_id)
    if meeting is None:
        return []
    new = db.item_embeddings_for_meeting(meeting_id, "decision")
    prior = db.item_embeddings("decision", exclude_meeting=meeting_id)
    prior = [(p, v) for p, v in prior if p["m_date"] <= meeting["meeting_date"]]
    if not new or not prior:
        return []

    created: list[str] = []
    for cur, vec in new:
        scored = sorted(((_cos(vec, v), p) for p, v in prior), key=lambda x: -x[0])
        cands = [p for s, p in scored[:CANDIDATES] if s >= MIN_SIMILARITY]
        if not cands:
            continue
        if len(cands) > 1:
            try:
                order = ai.rerank(cur["text"], [c["text"] for c in cands], top_n=CONFIRM_TOP)
                cands = [cands[i] for i, _score in order]
            except Exception as e:  # noqa: BLE001 - fall back to embedding order
                log.warning("rerank failed: %s", type(e).__name__)
                cands = cands[:CONFIRM_TOP]
        for prev in cands[:CONFIRM_TOP]:
            try:
                r = ai.chat(conflict_messages(
                    {"decision": prev["text"], "quote": prev["evidence_quote"], "meeting_date": prev["m_date"]},
                    {"decision": cur["text"], "quote": cur["evidence_quote"], "meeting_date": meeting["meeting_date"]},
                ), max_tokens=120, temperature=0.0)
            except Exception as e:  # noqa: BLE001
                log.warning("conflict check failed: %s", type(e).__name__)
                continue
            verdict = _parse(r.text)
            if verdict is None or not verdict.contradicts:
                continue
            cid = db.add_contradiction(
                meeting_id=meeting_id, previous_meeting_id=prev["meeting_id"], current_item_id=cur["id"],
                previous_item_id=prev["id"], source="cross_meeting", topic=verdict.topic or "Decision",
                current=cur["text"], previous=prev["text"], current_evidence=cur["evidence_quote"],
                previous_evidence=prev["evidence_quote"], explanation=verdict.explanation or None,
            )
            created.append(cid)
            # The notes' own "last week we agreed X" line describes the same reversal; keep one card.
            db.drop_in_meeting_duplicate(meeting_id, cur["evidence_quote"])
            db.notify("managers", "contradiction",
                      f"Decision conflict: '{cur['text']}' ({meeting['meeting_date']}) contradicts '{prev['text']}' ({prev['m_date']}).",
                      link=f"/manager#conflict-{cid}", dedupe_key=f"conflict:{cur['id']}:{prev['id']}")
            break
    return created
