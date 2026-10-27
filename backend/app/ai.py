"""AI provider selection.

live    Qualcomm Cloud AI Playground (the only mode for the real demo).
replay  development without a key: recorded or hand-written replies for the bundled demo
        notes, plus deterministic stand-ins for embeddings and the conflict check. Always
        badged "Replay (dev)" in the UI. Never presented as Qualcomm output.

With QUALCOMM_RECORD=1 the live provider also saves its extraction replies to
fixtures/replay/, so a connectivity-loss fallback replays real Qualcomm output.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

from .config import ROOT, Settings
from .prompts import CALLOUT_SYSTEM, CONFLICT_SYSTEM, EXTRACTION_SYSTEM, notes_from_messages
from .qualcomm import ChatResult, Qualcomm, QualcommError

REPLAY_DIR = ROOT / "fixtures" / "replay"          # hand-written dev replies (used by tests)
RECORDED_DIR = ROOT / "data" / "recorded"          # real Qualcomm replies, saved with QUALCOMM_RECORD=1


def notes_key(notes: str) -> str:
    """Whitespace-insensitive key, so pasted notes match even if line breaks or spaces differ."""
    return hashlib.sha256(" ".join(notes.split()).encode()).hexdigest()[:12]


_STOP = {"the", "and", "for", "with", "our", "use", "will", "this", "that", "from", "first", "deploy", "launch"}


def _notes_from(messages: list[dict]) -> str:
    return notes_from_messages(messages)


def _hash_vec(text: str, dims: int = 256) -> list[float]:
    v = [0.0] * dims
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        if len(tok) < 3:
            continue
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dims] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class ReplayAI:
    mode = "replay"
    model = "replay (dev)"

    def __init__(self, s: Settings, prefer_recorded: bool = False):
        self.s = s
        self.prefer_recorded = prefer_recorded

    def chat(self, messages: list[dict], **_: object) -> ChatResult:
        system = messages[0]["content"]
        if system == EXTRACTION_SYSTEM:
            notes = _notes_from(messages)
            name = f"extract-{notes_key(notes)}.json"
            path = RECORDED_DIR / name if self.prefer_recorded and (RECORDED_DIR / name).exists() else REPLAY_DIR / name
            if not path.exists():
                raise QualcommError("NO_REPLAY", "Replay mode only knows the bundled demo meetings. Add QUALCOMM_API_KEY for live extraction.", False)
            data = json.loads(path.read_text(encoding="utf-8"))
            return ChatResult(text=data["reply"], tool_arguments=None, model=data.get("model", self.model),
                              latency_ms=0, finish_reason="stop", prompt_tokens=None, completion_tokens=None)
        if system == CONFLICT_SYSTEM:
            payload = json.loads(messages[1]["content"])
            a, b = payload["earlier_decision"]["decision"], payload["new_decision"]["decision"]
            words = lambda s: set(re.findall(r"[a-z]{2,}", s.lower()))  # noqa: E731
            ta, tb = words(a), words(b)
            # Same action on the same subject, but a different choice ("on Azure" vs "on AWS").
            same_subject = bool((ta & tb) - {"on", "to", "in", "the", "we"})
            different = bool((ta ^ tb) - _STOP - {"on", "to", "in"})
            contradicts = same_subject and different and len(ta ^ tb) <= 4
            shared = (ta & tb) - {"on", "to", "in", "the", "we"}
            reply = {"contradicts": contradicts, "topic": " ".join(sorted(shared))[:40] or "decision",
                     "explanation": "Replay heuristic: same subject, different choice." if contradicts else "Replay heuristic: no conflict."}
            return ChatResult(json.dumps(reply), None, self.model, 0, "stop", None, None)
        if system == CALLOUT_SYSTEM:
            raise QualcommError("NO_REPLAY", "Callout uses the rule-based sentence in replay mode.", False)
        raise QualcommError("NO_REPLAY", "Unknown prompt in replay mode.", False)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vec(t) for t in texts]

    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[tuple[int, float]]:
        q = _hash_vec(query)
        scores = [(i, sum(a * b for a, b in zip(q, _hash_vec(d)))) for i, d in enumerate(documents)]
        return sorted(scores, key=lambda x: -x[1])[:top_n]

    def status(self) -> dict:
        return {"mode": self.mode, "model": self.model, "reason": "No QUALCOMM_API_KEY: development replay only."}


class LiveAI:
    mode = "live"

    def __init__(self, s: Settings):
        self.q = Qualcomm(s)
        self.s = s
        self.record = os.environ.get("QUALCOMM_RECORD", "").lower() in ("1", "true", "yes")
        self.last_error: str | None = None

    @property
    def model(self) -> str:
        return self.q.model

    def chat(self, messages: list[dict], **kw) -> ChatResult:
        try:
            r = self.q.chat(messages, **kw)
        except QualcommError as e:
            self.last_error = e.code
            raise
        self.last_error = None
        if self.record and messages[0]["content"] == EXTRACTION_SYSTEM and r.text:
            RECORDED_DIR.mkdir(parents=True, exist_ok=True)
            notes = _notes_from(messages)
            (RECORDED_DIR / f"extract-{notes_key(notes)}.json").write_text(
                json.dumps({"source": "recorded live Qualcomm reply", "model": r.model, "reply": r.text}, indent=1), encoding="utf-8")
        return r

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.q.embed(texts)

    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[tuple[int, float]]:
        return self.q.rerank(query, documents, top_n)

    def status(self) -> dict:
        return {"mode": self.mode, "model": self.model, "endpoint": self.s.qualcomm_endpoint,
                "client": self.s.qualcomm_client, "structured_mode": self.s.structured_mode, "last_error": self.last_error}


def build_ai(s: Settings):
    if os.environ.get("QUALCOMM_REPLAY", "").lower() in ("1", "true", "yes"):
        return ReplayAI(s, prefer_recorded=True)  # offline fallback: real recordings first
    if not s.qualcomm_api_key:
        return ReplayAI(s)
    return LiveAI(s)
