"""Risk propagation: how far one slip spreads, before it happens.

    d_origin = s
    d_j      = max(0, max over predecessors p of d_p - slack_j)

Slack is a task's spare time: the days between its latest predecessor's deadline and its
own, minus one day to do the work. A task with no date of its own ("once Raj finishes")
starts as soon as its predecessor ends, so it has no slack. A manager can override slack.
Done tasks absorb any delay. Days at risk is the largest delay reached; teams affected
counts the owner teams with a delay above zero, the origin included.
"""

from __future__ import annotations

import datetime as dt

WORK_DAYS = 1  # assumed time to do a task once its input arrives
MAX_DELAY = 10


def _date(i: dict) -> dt.date | None:
    return dt.date.fromisoformat(i["deadline_date"]) if i.get("deadline_date") else None


def slack(actions: list[dict]) -> dict[str, dict]:
    """Per task: {"days": n, "source": "auto" | "manual" | "none", "why": "..."}."""
    by_id = {a["id"]: a for a in actions}
    out = {}
    for a in actions:
        preds = [by_id[p] for p in a["depends_on"] if p in by_id]
        if a.get("slack_days") is not None:
            out[a["id"]] = {"days": int(a["slack_days"]), "source": "manual", "why": "Set by the manager."}
            continue
        own = _date(a)
        pred_dates = [d for d in (_date(p) for p in preds) if d]
        if not preds:
            out[a["id"]] = {"days": 0, "source": "none", "why": "Nothing upstream."}
        elif own is None or not pred_dates:
            out[a["id"]] = {"days": 0, "source": "auto", "why": "No date to compare with, so no spare time is assumed."}
        else:
            gap = (own - max(pred_dates)).days
            days = max(0, gap - WORK_DAYS)
            out[a["id"]] = {"days": days, "source": "auto",
                            "why": f"Due {gap} day{'s' if gap != 1 else ''} after its input, minus {WORK_DAYS} day of work."}
    return out


def _order(actions: list[dict]) -> list[str]:
    """Topological order (Kahn). Tasks caught in a cycle are left out rather than looping."""
    ids = {a["id"] for a in actions}
    indeg = {a["id"]: sum(1 for p in a["depends_on"] if p in ids) for a in actions}
    down: dict[str, list[str]] = {}
    for a in actions:
        for p in a["depends_on"]:
            if p in ids:
                down.setdefault(p, []).append(a["id"])
    queue = [i for i, n in indeg.items() if n == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for d in down.get(n, []):
            indeg[d] -= 1
            if indeg[d] == 0:
                queue.append(d)
    return order


def propagate(actions: list[dict], origin: str, days: int, slacks: dict[str, dict] | None = None) -> dict:
    by_id = {a["id"]: a for a in actions}
    slacks = slacks or slack(actions)
    delay: dict[str, int] = {}
    absorbed: dict[str, int] = {}  # delay that reached a task but its slack (or Done) soaked up
    for j in _order(actions):
        a = by_id[j]
        if j == origin:
            delay[j] = days
            continue
        incoming = max((delay.get(p, 0) for p in a["depends_on"] if p in by_id), default=0)
        if incoming <= 0:
            continue
        if a["status"] == "done":
            absorbed[j] = incoming
            continue
        d = max(0, incoming - slacks[j]["days"])
        if d:
            delay[j] = d
        else:
            absorbed[j] = incoming
    hit = {k: v for k, v in delay.items() if v > 0}
    teams = sorted({by_id[k]["team"] for k in hit if by_id[k]["team"]})
    unteamed = sum(1 for k in hit if not by_id[k]["team"])
    return {"days": days, "delays": hit, "absorbed": absorbed, "teams": teams, "teams_affected": len(teams),
            "unteamed": unteamed, "days_at_risk": max(hit.values(), default=0),
            "sentence": sentence(by_id[origin], days, hit, teams, unteamed)}


def sentence(origin: dict, days: int, hit: dict[str, int], teams: list[str], unteamed: int) -> str:
    who = origin["team"] or origin["owner"] or "This task"
    if days <= 0:
        return f"No delay on “{origin['text']}”."
    downstream = len(hit) - 1
    if downstream <= 0:
        return f"{who} slips {days} day{'s' if days != 1 else ''}: nothing downstream is affected."
    n = len(teams)
    worst = max(hit.values())
    extra = f" (+{unteamed} with no owner)" if unteamed else ""
    return (f"{who} slips {days} day{'s' if days != 1 else ''}: {downstream} downstream task{'s' if downstream != 1 else ''} late, "
            f"{n} team{'s' if n != 1 else ''}{extra}, {worst} day{'s' if worst != 1 else ''} at risk.")


def whatif(actions: list[dict], origin: str) -> dict:
    """Every delay from 0 to MAX_DELAY for one origin, so a slider can move without a round trip."""
    slacks = slack(actions)
    return {"origin": origin, "slack": slacks, "steps": [propagate(actions, origin, d, slacks) for d in range(MAX_DELAY + 1)]}
