"""Export the action table as CSV, or as a Jira bulk-create payload (POST /rest/api/2/issue/bulk).

Jira needs account ids for assignees, which the notes cannot give, so the owner goes in the
description and a label instead. Dependencies are listed in the description by task name.
"""

from __future__ import annotations

import csv
import io
import re

COLUMNS = ["Task", "Owner", "Team", "Deadline", "Deadline status", "Status", "Flags", "Verified", "Confidence",
           "Evidence", "Meeting", "Meeting date", "Depends on"]


def _cell(v: object) -> str:
    s = "" if v is None else str(v)
    # Spreadsheets run cells that start with these as formulas; the notes are untrusted text.
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _verified(i: dict) -> str:
    v = (i.get("verification") or {}).get("supported")
    return "yes" if v is True else "not checked" if v is None else "no"


def to_csv(actions: list[dict]) -> str:
    by_id = {a["id"]: a for a in actions}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for a in actions:
        w.writerow([_cell(x) for x in (
            a["text"], a["owner"] or "UNKNOWN", a["team"] or "", a["deadline_date"] or a["deadline_raw"] or "UNKNOWN",
            a["deadline_status"], a["status"], "; ".join(a["missing_info"]), _verified(a), f"{a['confidence']:.2f}",
            a["evidence_quote"], a["meeting"]["topic"], a["meeting"]["date"],
            "; ".join(by_id[d]["text"] for d in a["depends_on"] if d in by_id),
        )])
    return buf.getvalue()


def _label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def to_jira(actions: list[dict], project: str) -> dict:
    by_id = {a["id"]: a for a in actions}
    issues = []
    for a in actions:
        lines = [f"From the meeting “{a['meeting']['topic']}” ({a['meeting']['date']}).",
                 f"Evidence: {{quote}}{a['evidence_quote']}{{quote}}",
                 f"Owner in the notes: {a['owner'] or 'UNKNOWN'}" + (f" ({a['team']})" if a["team"] else ""),
                 f"Verified by Decision OS: {_verified(a)}, confidence {a['confidence']:.2f} (self-reported)."]
        deps = [by_id[d]["text"] for d in a["depends_on"] if d in by_id]
        if deps:
            lines.append("Depends on: " + "; ".join(deps))
        if a["missing_info"]:
            lines.append("Needs review: " + ", ".join(a["missing_info"]))
        labels = ["decision-os"] + [f"missing-{_label(m)}" for m in a["missing_info"]]
        if a["owner"]:
            labels.append(f"owner-{_label(a['owner'])}")
        fields = {"project": {"key": project}, "issuetype": {"name": "Task"}, "summary": a["text"][:255],
                  "description": "\n".join(lines), "labels": labels}
        if a["deadline_date"] and a["deadline_status"] == "exact":
            fields["duedate"] = a["deadline_date"]
        issues.append({"fields": fields})
    return {"issueUpdates": issues}
