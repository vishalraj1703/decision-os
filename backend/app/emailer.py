"""Real email notifications via Resend (spec 9.2): exactly three automatic triggers,
plus the Clarify Loop question a manager chooses to send.

1. Deadline within 24 hours, status not Done        -> employee
2. Deadline passed, status not Done                  -> employee, manager in cc
3. A dependency the employee was waiting on is done  -> employee

Every send is recorded in the emails table and deduplicated per trigger, and Resend's
idempotency key guards against double delivery. Resend's free tier only delivers to the
account's own address until a domain is verified, so EMAIL_OVERRIDE_TO routes every demo
email to one real inbox; the intended recipient is shown inside the email.

Templates are inline-styled HTML tables (Gmail-safe), rendered in Python. The spec names
React Email; it would need a Node renderer next to this Python sender, so we kept one
language for the send path. Swap the render functions if React Email is required.
"""

from __future__ import annotations

import html
import logging

from .config import Settings
from .db import DB
from .roster import MANAGERS, Person

log = logging.getLogger("decisionos.email")


def _layout(title: str, lines: list[str], cta_text: str, cta_url: str, intended: str | None) -> str:
    body = "".join(f'<p style="margin:0 0 12px;font-size:15px;line-height:1.5;color:#1f2933">{line}</p>' for line in lines)
    note = (f'<p style="margin:16px 0 0;font-size:12px;color:#7b8794">Demo routing: intended for {html.escape(intended)}.</p>'
            if intended else "")
    return f"""<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 0"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;border:1px solid #e5e7eb">
<tr><td style="background:#0e141b;padding:16px 24px;border-radius:8px 8px 0 0;color:#d6a95b;font-weight:bold;font-size:15px">Decision OS</td></tr>
<tr><td style="padding:24px">
<h1 style="margin:0 0 16px;font-size:20px;color:#111827">{html.escape(title)}</h1>
{body}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:8px"><tr><td style="background:#d6a95b;border-radius:6px">
<a href="{html.escape(cta_url)}" style="display:inline-block;padding:10px 18px;color:#1a1408;font-weight:bold;font-size:14px;text-decoration:none">{html.escape(cta_text)}</a>
</td></tr></table>
{note}
</td></tr></table></td></tr></table></body></html>"""


class Mailer:
    def __init__(self, s: Settings, db: DB):
        self.s = s
        self.db = db

    def _send(self, trigger: str, dedupe: str, item_id: str | None, to: Person, cc: list[Person], subject: str,
              title: str, lines: list[str], cta: str, link: str) -> str | None:
        eid = self.db.email_claim(dedupe, trigger, item_id, to.email, subject)
        if eid is None:
            return None  # this trigger already fired
        override = self.s.email_override_to
        if not self.s.resend_api_key:
            self.db.email_done(eid, "skipped", None, None, "RESEND_API_KEY not set")
            return eid
        if not override and to.email.endswith(".demo"):
            self.db.email_done(eid, "skipped", None, None, "Demo address has no inbox; set EMAIL_OVERRIDE_TO")
            return eid
        delivered = override or to.email
        cc_list = [] if override else [p.email for p in cc]
        intended = f"{to.name} <{to.email}>" + (f", cc {', '.join(p.name for p in cc)}" if cc else "") if override else None
        safe_lines = [html.escape(x) for x in lines]
        try:
            import resend

            resend.api_key = self.s.resend_api_key
            params = {"from": self.s.email_from, "to": [delivered], "subject": subject,
                      "html": _layout(title, safe_lines, cta, link, intended),
                      "text": "\n\n".join(lines + [f"{cta}: {link}"] + ([f"(Intended for {intended})"] if intended else []))}
            if cc_list:
                params["cc"] = cc_list
            r = resend.Emails.send(params, {"idempotency_key": dedupe[:256]})
            pid = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
            self.db.email_done(eid, "sent", delivered, pid, None)
            log.info("email sent trigger=%s id=%s", trigger, pid)
        except Exception as e:  # noqa: BLE001 - record and allow a later retry
            msg = f"{type(e).__name__}: {str(e)[:160]}"
            self.db.email_done(eid, "failed", delivered, None, msg)
            self.db.email_release(dedupe)
            log.warning("email failed trigger=%s err=%s", trigger, type(e).__name__)
        return eid

    # Trigger 1
    def due_tomorrow(self, task: dict, owner: Person) -> str | None:
        return self._send(
            "due_24h", f"due24:{task['id']}:{task['deadline_date']}", task["id"], owner, [],
            f"Due tomorrow: {task['text']}", "Your task is due tomorrow",
            [f"Hi {owner.name},", f"“{task['text']}” is due on {task['deadline_date']}.",
             "Mark it done, or flag it blocked so your manager knows before the deadline passes."],
            "Open your tasks", f"{self.s.app_url}/me#{task['id']}",
        )

    # Trigger 2
    def overdue(self, task: dict, owner: Person, downstream: list[dict]) -> str | None:
        blocks = ", ".join(f"{d['owner'] or 'UNKNOWN'}'s “{d['text']}”" for d in downstream)
        lines = [f"Hi {owner.name},", f"“{task['text']}” was due on {task['deadline_date']} and is not marked done."]
        if blocks:
            lines.append(f"This is blocking {blocks} downstream.")
        return self._send(
            "overdue", f"overdue:{task['id']}:{task['deadline_date']}", task["id"], owner, MANAGERS,
            f"Overdue: {task['text']}" + (" (blocking downstream work)" if blocks else ""),
            "Task overdue", lines, "Open the manager dashboard", f"{self.s.app_url}/manager#row-{task['id']}",
        )

    # Clarify Loop: sent by a manager, once per item, flag and person
    def clarify(self, item: dict, flag: str, to: Person, question: str, sender: str) -> str | None:
        return self._send(
            "clarify", f"clarify:{item['id']}:{flag}:{to.id}", item["id"], to, [],
            f"Question about: {item['text']}", "A question from your manager",
            [f"Hi {to.name},", f"{sender} asks: {question}", f"From the notes: “{item['evidence_quote']}”",
             "Reply to your manager with the answer."],
            "Open Decision OS", f"{self.s.app_url}/me",
        )

    # Trigger 3
    def dependency_done(self, upstream: dict, task: dict, owner: Person) -> str | None:
        return self._send(
            "dependency_done", f"depdone:{upstream['id']}:{task['id']}", task["id"], owner, [],
            f"You can start: {task['text']}", "A dependency is complete",
            [f"Hi {owner.name},", f"{upstream['owner'] or 'Your teammate'}'s “{upstream['text']}” is done.",
             f"You can start “{task['text']}”."],
            "Open the task", f"{self.s.app_url}/me#{task['id']}",
        )
