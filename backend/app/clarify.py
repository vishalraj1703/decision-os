"""Clarify Loop: every flag comes with the one question to send, and who to send it to.

Templates, not AI: the question must say exactly what is missing and nothing else.
Who to ask:
- a missing owner goes to whoever the sentence names ("Ask Meera ..."), else the team it
  mentions ("finance"), else the people who own other work from the same meeting;
- a missing or unconfirmed date goes to the task's owner.
"""

from __future__ import annotations

import datetime as dt
import re

from . import dates
from .evidence import word_in
from .roster import PEOPLE, TEAM_ALIASES, Person


def _recipients_for_owner(item: dict, meeting_items: list[dict]) -> tuple[list[Person], str]:
    sentence = item["evidence_quote"]
    named = [p for p in PEOPLE if p.role == "employee" and word_in(p.name, sentence)]
    if named:
        return named, "named in the sentence"
    low = sentence.lower()
    teams = {team for alias, team in TEAM_ALIASES.items() if re.search(rf"\b{re.escape(alias)}\b", low)}
    if teams:
        return [p for p in PEOPLE if p.team in teams and p.role == "employee"], f"{', '.join(sorted(teams))} team"
    owners = {i["owner_user_id"] for i in meeting_items if i["owner_user_id"] and i["id"] != item["id"]}
    return [p for p in PEOPLE if p.id in owners], "attendees with other work from this meeting"


def drafts(item: dict, meeting_items: list[dict]) -> list[dict]:
    """One draft per open flag on a review item."""
    out = []
    what = f"“{item['text']}”"
    kind = "risk" if item["kind"] == "risk" else "task"
    due = ""
    if item["deadline_date"]:
        due = f", due {dates.fmt(dt.date.fromisoformat(item['deadline_date']))}"
    owner = next((p for p in PEOPLE if p.id == item["owner_user_id"]), None)
    for flag in item["missing_info"]:
        if flag == "owner":
            to, why = _recipients_for_owner(item, meeting_items)
            q = f"Who owns the {kind} {what}{due}? The notes do not name anyone for it."
        elif flag == "deadline":
            to, why = ([owner], "owner of the task") if owner else _recipients_for_owner(item, meeting_items)
            q = f"When will {what} be done? The notes do not give a date."
        elif flag == "deadline_confirmation":
            to, why = ([owner], "owner of the task") if owner else _recipients_for_owner(item, meeting_items)
            q = (f"For {what}, the notes say “{item['deadline_raw']}”. Does that mean "
                 f"{dates.fmt(dt.date.fromisoformat(item['deadline_date']))}?") if item["deadline_date"] else \
                f"What date does “{item['deadline_raw']}” mean for {what}?"
        else:
            continue
        out.append({"flag": flag, "question": q, "to": [{"id": p.id, "email": p.email, "name": p.name, "team": p.team} for p in to],
                    "why": why})
    return out
