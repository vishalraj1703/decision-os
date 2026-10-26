"""Deadline cascade (spec 5.5): overdue detection and downstream risk propagation.

An action is overdue when its deadline date is before "today" and it is not Done.
Anything that depends (directly or transitively) on an overdue or Blocked action is at risk.
Colors (status only, never team): green done, red blocked/overdue, orange at risk or needs
review, grey pending.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .db import DB


def today(db: DB, tz: str) -> tuple[dt.date, bool]:
    """Real local date, or the simulated date set for the demo."""
    sim = db.get_meta("simulated_date")
    if sim:
        return dt.date.fromisoformat(sim), True
    return dt.datetime.now(ZoneInfo(tz)).date(), False


def compute(items: list[dict], on: dt.date) -> dict[str, tuple[bool, bool]]:
    actions = {i["id"]: i for i in items if i["kind"] == "action" and i["review_state"] != "discarded"}
    overdue = {
        iid for iid, i in actions.items()
        if i["deadline_date"] and i["status"] != "done" and dt.date.fromisoformat(i["deadline_date"]) < on
    }
    sources = overdue | {iid for iid, i in actions.items() if i["status"] == "blocked"}
    downstream: dict[str, list[str]] = {}
    for iid, i in actions.items():
        for up in i["depends_on"]:
            downstream.setdefault(up, []).append(iid)
    at_risk: set[str] = set()
    stack = list(sources)
    while stack:
        up = stack.pop()
        for d in downstream.get(up, []):
            if d not in at_risk and actions[d]["status"] != "done":
                at_risk.add(d)
                stack.append(d)
    return {iid: (iid in overdue, iid in at_risk and iid not in sources) for iid in actions}


def color(i: dict) -> str:
    if i["status"] == "done":
        return "green"
    if i["status"] == "blocked" or i["overdue"]:
        return "red"
    if i["at_risk"] or i["review_state"] == "needs_review":
        return "orange"
    return "grey"


def recompute(db: DB, tz: str) -> tuple[dt.date, list[dict], list[dict]]:
    """Persist flags; return (today, newly overdue items, newly at-risk items)."""
    on, _ = today(db, tz)
    items = db.items()
    before = {i["id"]: (i["overdue"], i["at_risk"]) for i in items}
    flags = compute(items, on)
    db.set_flags(flags)
    by_id = {i["id"]: i for i in items}
    newly_overdue = [by_id[k] for k, (o, _r) in flags.items() if o and not before[k][0]]
    newly_risk = [by_id[k] for k, (_o, r) in flags.items() if r and not before[k][1]]
    return on, newly_overdue, newly_risk
