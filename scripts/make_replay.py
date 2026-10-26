"""Write HAND-WRITTEN development replay replies for the two demo meetings.

These imitate a Qualcomm reply so the UI can be built without a key. They include one
typical small-model mistake (assigning the finance follow-up to Raj) so the honesty
backstop is visible. Replace them with real recordings: run the backend with
QUALCOMM_RECORD=1 and a key, then extract the demo notes once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai import REPLAY_DIR, notes_key  # noqa: E402

M0 = {
    "meeting_topic": "Checkout release",
    "decisions": [
        {"decision": "Deploy on Azure", "owner": "UNKNOWN", "deadline": "UNKNOWN",
         "evidence_quote": "We agreed to deploy on Azure.", "confidence": 0.95, "missing_info": ["owner", "deadline"]},
        {"decision": "Release checkout on Oct 30", "owner": "UNKNOWN", "deadline": "Oct 30",
         "evidence_quote": "The checkout release is planned for Oct 30.", "confidence": 0.8, "missing_info": ["owner"]},
    ],
    "actions": [
        {"id": "a1", "task": "Approve the API contract", "owner": "Ravi", "deadline": "Oct 27", "dependencies": [],
         "evidence_quote": "Ravi will approve the API contract by Oct 27.", "confidence": 0.93, "missing_info": []},
        {"id": "a2", "task": "Build the checkout flow", "owner": "Asha", "deadline": "Oct 28", "dependencies": ["a1"],
         "evidence_quote": "Asha will build the checkout flow once Ravi approves the API contract, by Oct 28.",
         "confidence": 0.9, "missing_info": []},
        {"id": "a3", "task": "Run QA on checkout", "owner": "Meera", "deadline": "Oct 29", "dependencies": ["a2"],
         "evidence_quote": "Meera will run QA on checkout after Asha finishes, by Oct 29.", "confidence": 0.9, "missing_info": []},
    ],
    "risks": [],
    "contradictions": [],
}

M1 = {
    "meeting_topic": "Checkout release",
    "decisions": [
        {"decision": "Deploy on AWS", "owner": "UNKNOWN", "deadline": "UNKNOWN",
         "evidence_quote": "We agreed to deploy on AWS.", "confidence": 0.95, "missing_info": ["owner", "deadline"]},
    ],
    "actions": [
        {"id": "a1", "task": "Build payment API", "owner": "Raj", "deadline": "Friday (relative - needs confirmation)",
         "dependencies": [], "evidence_quote": "Raj said the payment API will be ready by Friday.", "confidence": 0.92,
         "missing_info": []},
        {"id": "a2", "task": "Test payment API", "owner": "Priya", "deadline": "After API complete", "dependencies": ["a1"],
         "evidence_quote": "Priya will test it once Raj finishes.", "confidence": 0.88, "missing_info": []},
        # Typical mistake: the model guesses an owner the sentence never names.
        {"id": "a3", "task": "Follow up with finance on the hosting budget", "owner": "Raj", "deadline": "UNKNOWN",
         "dependencies": [], "evidence_quote": "Someone needs to follow up with finance.", "confidence": 0.6,
         "missing_info": ["deadline"]},
    ],
    "risks": [
        {"risk": "Hosting budget not approved", "owner": "UNKNOWN", "deadline": "UNKNOWN", "severity": "high",
         "evidence_quote": "The finance team hasn't approved the hosting budget yet.", "confidence": 0.85,
         "missing_info": ["owner", "deadline"]},
    ],
    "contradictions": [
        {"topic": "Cloud provider", "current": "AWS", "previous": "Azure",
         "previous_evidence": "Last week, the team had agreed to deploy on Azure.", "current_evidence": "We agreed to deploy on AWS."},
    ],
}


def write(name: str, reply: dict) -> None:
    notes = (ROOT / "fixtures" / f"{name}.txt").read_text(encoding="utf-8")
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    path = REPLAY_DIR / f"extract-{notes_key(notes)}.json"
    path.write_text(json.dumps({"source": "HAND-WRITTEN dev replay, not a Qualcomm output", "model": "replay (dev)",
                                "reply": json.dumps(reply)}, indent=1), encoding="utf-8")
    print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    write("demo_meeting_0", M0)
    write("demo_meeting_1", M1)
