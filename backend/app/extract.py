"""Feature 1-3 engine: Qualcomm extraction -> strict schema -> evidence and honesty checks.

Flow: one call; if the reply is not valid JSON for the schema, or a quote is not in the
notes, one corrective call (spec: retry once). After that, items whose quote still cannot
be found are rejected (shown to the manager, never silently kept).

Honesty backstops in code, because a prompt alone does not stop an 8B model guessing:
- an owner must be named in the item's own evidence sentence, else UNKNOWN;
- deadline wording must appear in the evidence sentence, else UNKNOWN;
- missing_info is recomputed from the final fields so it cannot disagree with them.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from . import dates
from .evidence import locate, sentence_around, word_in
from .prompts import EXTRACTION_TOOL, extraction_messages, repair_messages
from .qualcomm import QualcommError
TEAM_WORDS = {"the", "team", "finance", "platform", "product", "quality", "qa", "everyone", "someone", "we"}
from .schema import UNKNOWN, AIExtraction

log = logging.getLogger("decisionos.extract")


class ExtractionFailed(Exception):
    def __init__(self, code: str, message: str, retryable: bool, details: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or []


@dataclass
class CheckedItem:
    kind: str  # action | decision | risk
    ref: str
    text: str
    owner: str | None
    deadline_raw: str
    deadline: dates.Deadline
    dependencies: list[str]
    severity: str | None
    evidence_quote: str
    ev_start: int
    ev_end: int
    confidence: float
    missing_info: list[str]
    checks: list[str] = field(default_factory=list)


@dataclass
class CheckedContradiction:
    topic: str
    current: str
    previous: str
    current_evidence: str
    previous_evidence: str


@dataclass
class ExtractOutcome:
    topic: str
    items: list[CheckedItem]
    contradictions: list[CheckedContradiction]
    rejected: list[dict]
    attempts: int
    latency_ms: int
    model: str


def _parse(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0]
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        a, b = body.find("{"), body.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("reply is not JSON") from None
        obj = json.loads(body[a : b + 1])
    if not isinstance(obj, dict):
        raise ValueError("reply JSON is not an object")
    return obj


def _validate(reply_text: str, tool_args: dict | None, notes: str) -> tuple[AIExtraction | None, list[str]]:
    try:
        data = tool_args if tool_args is not None else _parse(reply_text)
        ext = AIExtraction.model_validate(data)
    except (ValueError, ValidationError) as e:
        msg = str(e)
        if isinstance(e, ValidationError):
            msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:10])
        return None, [msg[:500]]
    errors = []
    for group in ("decisions", "actions", "risks"):
        for k, it in enumerate(getattr(ext, group)):
            if locate(it.evidence_quote, notes) is None:
                errors.append(f"{group}[{k}].evidence_quote is not an exact sentence from the notes: {it.evidence_quote!r}")
    return ext, errors


def _owner_check(owner: str, sentence: str) -> tuple[str | None, str | None]:
    if owner == UNKNOWN:
        return None, None
    first = owner.split()[0]
    if word_in(owner, sentence) or word_in(first, sentence):
        if first.lower() in TEAM_WORDS:
            return None, f"'{owner}' is a team, not a named owner, so it was set to UNKNOWN."
        return owner.strip(), None
    return None, f"Owner '{owner}' is not named in the source sentence, so it was set to UNKNOWN."


def _deadline_check(deadline: str, sentence: str) -> tuple[str, str | None]:
    if deadline == UNKNOWN:
        return UNKNOWN, None
    core = deadline.split("(")[0].strip().strip(".")
    tokens = [t for t in core.replace(",", " ").split() if t.lower() not in ("by", "on", "the", "before", "due")]
    if core and (word_in(core, sentence) or (tokens and all(word_in(t, sentence) for t in tokens))):
        return core, None
    if any(w in core.lower() for w in ("after", "once", "when")):
        return core, None
    return UNKNOWN, f"Deadline '{deadline}' is not in the source sentence, so it was set to UNKNOWN."


def _check(ext: AIExtraction, notes: str, meeting_date: dt.date) -> tuple[list[CheckedItem], list[CheckedContradiction], list[dict]]:
    items: list[CheckedItem] = []
    rejected: list[dict] = []
    rows = [("decision", d.decision, d, None) for d in ext.decisions] + \
           [("action", a.task, a, a) for a in ext.actions] + \
           [("risk", r.risk, r, None) for r in ext.risks]
    counters = {"decision": 0, "risk": 0}
    for kind, text, it, act in rows:
        span = locate(it.evidence_quote, notes)
        if span is None:
            rejected.append({"kind": kind, "text": text, "reason": "Evidence sentence not found in the notes."})
            continue
        s, e = span
        ss, se = sentence_around(notes, s, e)
        sentence = notes[ss:se]
        checks: list[str] = []
        owner, why = _owner_check(it.owner, sentence)
        if why:
            checks.append(why)
        deadline_raw, why = _deadline_check(it.deadline, sentence)
        if why:
            checks.append(why)
        dl = dates.normalize(deadline_raw, meeting_date)
        deps = list(act.dependencies) if act else []
        if dl.status == "after_dependency" and not deps:
            dl = dates.Deadline(None, "unknown", "Depends on something the notes do not identify as a task.")
        missing = []
        if owner is None:
            missing.append("owner")
        if dl.status == "unknown":
            missing.append("deadline")
        elif dl.status == "needs_confirmation":
            missing.append("deadline_confirmation")
        if kind == "risk" and getattr(it, "severity", UNKNOWN) == UNKNOWN:
            pass  # severity is informational; not a blocker for review
        if kind == "action":
            ref = act.id
        else:
            counters[kind] += 1
            ref = f"{kind[0]}{counters[kind]}"
        items.append(CheckedItem(
            kind=kind, ref=ref, text=text, owner=owner, deadline_raw=deadline_raw, deadline=dl,
            dependencies=deps, severity=getattr(it, "severity", None) if kind == "risk" else None,
            evidence_quote=notes[s:e], ev_start=ss, ev_end=se, confidence=it.confidence,
            missing_info=missing, checks=checks,
        ))

    # Dependencies must point at real actions of this meeting; no self-links.
    action_refs = {i.ref for i in items if i.kind == "action"}
    for i in items:
        bad = [d for d in i.dependencies if d not in action_refs or d == i.ref]
        if bad:
            i.checks.append(f"Dropped unknown dependency {', '.join(bad)}.")
        i.dependencies = [d for d in dict.fromkeys(i.dependencies) if d in action_refs and d != i.ref]

    contradictions: list[CheckedContradiction] = []
    for c in ext.contradictions:
        cur, prev = locate(c.current_evidence, notes), locate(c.previous_evidence, notes)
        if cur and prev:
            contradictions.append(CheckedContradiction(c.topic, c.current, c.previous, notes[cur[0]:cur[1]], notes[prev[0]:prev[1]]))
        else:
            rejected.append({"kind": "contradiction", "text": c.topic, "reason": "Quoted sentences not found in the notes."})
    return items, contradictions, rejected


def run(ai, notes: str, meeting_date: dt.date, mode: str = "json") -> ExtractOutcome:
    base = extraction_messages(notes, meeting_date.isoformat(), mode)
    tool = EXTRACTION_TOOL if mode == "tool" else None
    latency = 0
    attempts = 0
    last_errors: list[str] = []
    messages = base
    best: AIExtraction | None = None
    model = getattr(ai, "model", "unknown")
    while attempts < 2:
        attempts += 1
        try:
            r = ai.chat(messages, tool=tool)
        except QualcommError as e:
            if e.retryable and attempts < 2:
                last_errors = [e.message]
                continue
            raise ExtractionFailed(e.code, e.message, e.retryable) from None
        latency += r.latency_ms
        model = r.model
        if r.finish_reason == "length":
            last_errors = ["reply was cut off at the output limit; return a shorter JSON object"]
            messages = repair_messages(base, r.text or "", last_errors)
            continue
        ext, errors = _validate(r.text, r.tool_arguments if mode == "tool" else None, notes)
        if ext is not None:
            best = ext
        if not errors:
            break
        last_errors = errors
        log.info("extraction attempt %d invalid: %d problems", attempts, len(errors))
        messages = repair_messages(base, r.text or json.dumps(r.tool_arguments or {}), errors)

    if best is None:
        raise ExtractionFailed("INVALID_AI_RESPONSE", "The AI reply could not be used after one corrective retry. Nothing was saved.",
                               True, last_errors)
    items, contradictions, rejected = _check(best, notes, meeting_date)
    return ExtractOutcome(topic=best.meeting_topic, items=items, contradictions=contradictions, rejected=rejected,
                          attempts=attempts, latency_ms=latency, model=model)
