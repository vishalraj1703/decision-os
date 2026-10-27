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
        # A suggestion the model turns into a task; the Verifier removes it.
        {"id": "a4", "task": "Book offsite venue for the launch party", "owner": "Arun", "deadline": "UNKNOWN",
         "dependencies": [], "evidence_quote": "Maybe Arun could look at offsite venues for the launch party.",
         "confidence": 0.5, "missing_info": ["deadline"]},
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


SA = {
    "meeting_topic": "Mobile app beta",
    "decisions": [
        {"decision": "Launch the beta on Android first", "owner": "UNKNOWN", "deadline": "UNKNOWN",
         "evidence_quote": "We agreed to launch the beta on Android first.", "confidence": 0.94, "missing_info": ["owner", "deadline"]},
        {"decision": "Beta launch on Nov 5", "owner": "UNKNOWN", "deadline": "Nov 5",
         "evidence_quote": "The beta launch is planned for Nov 5.", "confidence": 0.8, "missing_info": ["owner"]},
    ],
    "actions": [
        {"id": "a1", "task": "Approve the testing budget", "owner": "Kavya", "deadline": "Oct 27", "dependencies": [],
         "evidence_quote": "Kavya will approve the testing budget by Oct 27.", "confidence": 0.93, "missing_info": []},
        {"id": "a2", "task": "Write the test plan", "owner": "Meera", "deadline": "Oct 29", "dependencies": ["a1"],
         "evidence_quote": "Meera will write the test plan once Kavya approves the budget, by Oct 29.", "confidence": 0.9,
         "missing_info": []},
    ],
    "risks": [],
    "contradictions": [],
}

SB = {
    "meeting_topic": "Mobile app beta",
    "decisions": [
        {"decision": "Launch the beta on iOS first", "owner": "UNKNOWN", "deadline": "UNKNOWN",
         "evidence_quote": "We decided to launch the beta on iOS first.", "confidence": 0.93, "missing_info": ["owner", "deadline"]},
    ],
    "actions": [
        {"id": "a1", "task": "Finish the login screen", "owner": "Asha", "deadline": "Friday", "dependencies": [],
         "evidence_quote": "Asha will finish the login screen by Friday.", "confidence": 0.9, "missing_info": []},
        {"id": "a2", "task": "Test the login screen", "owner": "Priya", "deadline": "after Asha finishes", "dependencies": ["a1"],
         "evidence_quote": "Priya will test the login screen after Asha finishes.", "confidence": 0.88, "missing_info": []},
        # Typical mistake: guessing an owner for "someone".
        {"id": "a3", "task": "Update the app store listing", "owner": "Asha", "deadline": "UNKNOWN", "dependencies": [],
         "evidence_quote": "Someone needs to update the app store listing.", "confidence": 0.55, "missing_info": ["deadline"]},
    ],
    "risks": [
        {"risk": "Push notification server may not be ready in time", "owner": "UNKNOWN", "deadline": "UNKNOWN",
         "severity": "medium", "evidence_quote": "Ravi said the push notification server might not be ready in time.",
         "confidence": 0.8, "missing_info": ["owner"]},
    ],
    "contradictions": [],
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
    write("sample_meeting_A", SA)
    write("sample_meeting_B", SB)
