"""Accuracy against the hand-labelled gold set (fixtures/gold), layer by layer.

Each note is extracted once and measured at three layers:
  pass1   the Extractor's reply as written (one prompt, nothing checked)
  code    after the code checks (quotes, owners and deadlines must be in the sentence)
  full    after the Verifier as well (what the product shows)

The scoring is plain code so the numbers can be re-checked. Rules: fixtures/gold/README.md.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path

from . import extract, verifier
from .config import ROOT
from .redact import redact
from .schema import UNKNOWN

GOLD_DIR = ROOT / "fixtures" / "gold"
GOLD_FILE = GOLD_DIR / "gold.json"
RESULTS_FILE = GOLD_DIR / "results.json"
LAYERS = ("pass1", "code", "full")
LAYER_LABELS = {"pass1": "Pass 1 alone (one prompt)", "code": "+ code checks", "full": "+ Verifier (Decision OS)"}

_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def load_gold(path: Path = GOLD_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["notes"]


def _norm(s: str | None) -> str:
    s = (s or "").translate(_FOLD).lower()
    s = re.sub(r"[^\w\s\[\]']", " ", s)
    return " ".join(s.split())


def same_evidence(pred: str, gold: str) -> bool:
    p, g = _norm(pred), _norm(gold)
    return bool(p and g) and (g in p or (len(p) >= 12 and p in g))


def _person(v: str | None) -> str | None:
    s = (v or "").strip()
    return None if not s or s.upper() == UNKNOWN else s.split()[0].lower()


def _known(v: str | None) -> bool:
    return bool(v) and v.strip().upper() != UNKNOWN


def score_note(gold: dict, predicted: list[dict]) -> dict:
    """predicted: [{kind, text, owner, deadline, evidence}]. Returns counts and the mistakes found."""
    unmatched = list(range(len(predicted)))
    matched: list[tuple[dict, dict]] = []
    for g in gold["items"]:
        hit = next((k for k in unmatched if predicted[k]["kind"] == g["kind"]
                    and same_evidence(predicted[k]["evidence"], g["evidence"])), None)
        if hit is not None:
            unmatched.remove(hit)
            matched.append((g, predicted[hit]))
    mistakes = []
    for k in unmatched:
        p = predicted[k]
        trap = any(same_evidence(p["evidence"], t) for t in gold.get("not_items", []))
        mistakes.append({"type": "invented item", "text": p["text"],
                         "why": "a suggestion, question or non-task" if trap else "not in the answer key"})
    for g, p in matched:
        if g["kind"] == "decision":
            continue
        bad = []
        gp, pp = _person(g["owner"]), _person(p["owner"])
        if pp and pp != gp:
            bad.append(f"owner {p['owner']} (key: {g['owner']})")
        if g["kind"] == "action" and _known(p["deadline"]) and not _known(g["deadline"]):
            bad.append(f"deadline {p['deadline']} (key: none stated)")
        if bad:
            mistakes.append({"type": "invented field", "text": p["text"], "why": "; ".join(bad)})
    wrong_items = len(unmatched) + sum(1 for m in mistakes if m["type"] == "invented field")
    lost = sum(1 for g, p in matched if g["kind"] != "decision" and _person(g["owner"]) and not _person(p["owner"]))
    return {"predicted": len(predicted), "gold": len(gold["items"]), "matched": len(matched),
            "hallucinations": wrong_items, "owners_lost": lost, "mistakes": mistakes,
            "found": [g["evidence"] for g, _ in matched]}


def summarize(per_note: list[dict]) -> dict:
    t = {k: sum(n[k] for n in per_note) for k in ("predicted", "gold", "matched", "hallucinations", "owners_lost")}

    def pct(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    return {**t, "precision": pct(t["matched"], t["predicted"]), "recall": pct(t["matched"], t["gold"]),
            "hallucination_rate": pct(t["hallucinations"], t["predicted"])}


def _row(kind: str, text: str, owner: str | None, deadline: str | None, evidence: str) -> dict:
    return {"kind": kind, "text": text, "owner": owner or UNKNOWN, "deadline": deadline or UNKNOWN, "evidence": evidence}


def run_layers(ai, notes: str, meeting_date: dt.date, mode: str = "json") -> dict:
    """One extraction, measured after each layer. Uses the same code path as the product."""
    text, masked = redact(notes)
    out = extract.run(ai, text, meeting_date, mode, verify=False)
    pass1 = [_row(r["kind"], r["text"], r["owner"], r["deadline"], r["evidence"]) for r in out.replay]
    code = [_row(i.kind, i.text, i.owner, i.deadline_raw, i.evidence_quote) for i in out.items]
    checked = copy.deepcopy(out.items)
    v = verifier.verify(ai, text, checked, meeting_date)
    removed = {id(i) for i, _ in v.removed}
    full = [_row(i.kind, i.text, i.owner, i.deadline_raw, i.evidence_quote) for i in checked if id(i) not in removed]
    dropped = [{"text": i.text, "evidence": i.evidence_quote, "reason": reason} for i, reason in v.removed]
    return {"pass1": pass1, "code": code, "full": full, "verify": v.summary(), "masked": masked, "dropped": dropped,
            "latency_ms": out.latency_ms + v.latency_ms, "model": out.model}


def evaluate(ai, gold: list[dict], mode: str = "json", progress=None) -> dict:
    per_layer: dict[str, list[dict]] = {k: [] for k in LAYERS}
    notes_out = []
    model = getattr(ai, "model", "unknown")
    for g in gold:
        if progress:
            progress(g)
        try:
            r = run_layers(ai, g["notes"], dt.date.fromisoformat(g["date"]), mode)
        except extract.ExtractionFailed as e:
            notes_out.append({"id": g["id"], "title": g["title"], "error": e.code})
            for k in LAYERS:  # a failed note counts as nothing extracted
                per_layer[k].append(score_note(g, []))
            continue
        model = r["model"]
        scores = {k: score_note(g, r[k]) for k in LAYERS}
        for k in LAYERS:
            per_layer[k].append(scores[k])
        caught = [m for m in scores["pass1"]["mistakes"]
                  if not any(m["text"] == x["text"] and m["type"] == x["type"] for x in scores["full"]["mistakes"])]
        # Right answers the code checks kept but the Verifier removed: the cost of being strict.
        lost = [next(({"text": d["text"], "why": d["reason"]} for d in r["dropped"] if same_evidence(d["evidence"], e)),
                     {"text": e, "why": "removed"}) for e in scores["code"]["found"] if e not in scores["full"]["found"]]
        notes_out.append({"id": g["id"], "title": g["title"], "latency_ms": r["latency_ms"], "verify": r["verify"]["status"],
                          "masked": r["masked"], "scores": {k: {x: v for x, v in s.items() if x not in ("mistakes", "found")}
                                                            for k, s in scores.items()},
                          "caught": caught, "remaining": scores["full"]["mistakes"], "lost": lost})
    return {
        "measured_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "model": model, "notes": len(gold), "gold_items": sum(len(g["items"]) for g in gold),
        "failed_notes": [n["id"] for n in notes_out if "error" in n],
        "layers": {k: {"label": LAYER_LABELS[k], **summarize(per_layer[k])} for k in LAYERS},
        "per_note": notes_out,
    }


def load_results(path: Path | None = None) -> dict | None:
    try:
        return json.loads((path or RESULTS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
