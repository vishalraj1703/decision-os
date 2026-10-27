"""Meeting Health Score: a published formula, so every point can be explained.

H = 100 x (0.30 O + 0.25 D + 0.20 V + 0.15 (1 - A) + 0.10 (1 - C))

O  share of tasks with a named owner
D  share of tasks with a confirmed exact deadline (Done tasks count as settled)
V  mean confidence of the items the Verifier confirmed (all items if none were verified)
A  share of items still carrying a flag (missing owner, deadline or confirmation)
C  share of decisions in an open conflict

It is computed from current state, so assigning an owner or resolving a conflict raises it.
"""

from __future__ import annotations

WEIGHTS = {"O": 0.30, "D": 0.25, "V": 0.20, "A": 0.15, "C": 0.10}
LABELS = {
    "O": "Tasks with an owner",
    "D": "Tasks with a confirmed date",
    "V": "Verified confidence",
    "A": "Items without flags",
    "C": "Decisions without conflict",
}


def _share(n: int, total: int) -> float:
    return n / total if total else 1.0


def score(items: list[dict], contradictions: list[dict]) -> dict:
    live = [i for i in items if i["review_state"] not in ("discarded", "superseded")]
    tasks = [i for i in live if i["kind"] == "action"]
    decisions = [i for i in live if i["kind"] == "decision"]

    owned = sum(1 for t in tasks if t["owner"])
    dated = sum(1 for t in tasks if t["status"] == "done" or (t["deadline_date"] and t["deadline_status"] == "exact"))
    verified = [i for i in live if (i.get("verification") or {}).get("supported") is True]
    basis = verified or live
    v = sum(i["confidence"] or 0 for i in basis) / len(basis) if basis else 1.0
    flagged = sum(1 for i in live if i["missing_info"])
    decision_ids = {d["id"] for d in decisions}
    in_conflict = {c["current_item_id"] for c in contradictions
                   if c["status"] == "open" and c["current_item_id"] in decision_ids}
    # Conflicts the notes state themselves ("last week we agreed X") have no item link; count them per card.
    unlinked = sum(1 for c in contradictions if c["status"] == "open" and not c["current_item_id"])
    conflicted = min(len(decisions), len(in_conflict) + unlinked)

    values = {
        "O": (_share(owned, len(tasks)), f"{owned} of {len(tasks)}" if tasks else "no tasks"),
        "D": (_share(dated, len(tasks)), f"{dated} of {len(tasks)}" if tasks else "no tasks"),
        "V": (v, f"mean of {len(basis)} {'verified ' if verified else ''}item{'s' if len(basis) != 1 else ''}"
              + ("" if verified or not live else " (none verified)")),
        "A": (_share(flagged, len(live)) if live else 0.0, f"{flagged} of {len(live)} flagged"),
        "C": (_share(conflicted, len(decisions)) if decisions else 0.0,
              f"{conflicted} of {len(decisions)} in conflict" if decisions else "no decisions"),
    }
    parts = []
    total = 0.0
    for k, w in WEIGHTS.items():
        value, detail = values[k]
        good = 1 - value if k in ("A", "C") else value  # A and C count against the score
        points = round(100 * w * good, 1)
        total += 100 * w * good
        parts.append({"key": k, "label": LABELS[k], "weight": w, "value": round(value, 3), "points": points,
                      "max": round(100 * w, 1), "detail": detail})
    return {"score": round(total), "parts": parts, "lost": round(100 - total, 1), "items": len(live)}
