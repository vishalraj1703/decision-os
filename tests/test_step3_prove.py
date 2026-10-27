"""Step 3: gold set and scoring, the recorded scoreboard, meeting purge, evidence fingerprints, demo note."""

import datetime as dt
import json

from app import gold
from app.db import evidence_hash
from app.redact import redact

from conftest import MANAGER, ScriptedAI, as_user, extract

GOLD = {g["id"]: g for g in gold.load_gold()}


def test_gold_set_is_well_formed():
    assert len(GOLD) == 10
    for g in GOLD.values():
        dt.date.fromisoformat(g["date"])
        masked = gold._norm(redact(g["notes"])[0])
        assert g["items"] and g["traps"], g["id"]
        for it in g["items"]:
            assert it["kind"] in ("action", "decision", "risk"), g["id"]
            assert gold._norm(it["evidence"]) in masked, (g["id"], it["evidence"])
        for t in g["not_items"]:
            assert gold._norm(t) in masked, (g["id"], t)
    assert sum(len(g["items"]) for g in GOLD.values()) == 39


def row(kind, evidence, owner="UNKNOWN", deadline="UNKNOWN", text=None):
    return {"kind": kind, "text": text or evidence[:30], "owner": owner, "deadline": deadline, "evidence": evidence}


def test_scoring_counts_inventions():
    g = GOLD["g01"]
    predicted = [
        row("action", "Priya will finish the API spec by Nov 4.", "Priya", "Nov 4"),                      # right
        row("action", "Ask Meera whether someone can close the vendor renewal by Nov 6.", "Meera", "Nov 6"),  # guessed owner
        row("action", "Maybe look at offsite options, Arun?", "Arun", text="Book offsite"),               # not a task
        row("decision", "We agreed to ship mobile first.", "Ravi"),                                        # decision owners not scored
    ]
    s = gold.score_note(g, predicted)
    assert (s["predicted"], s["gold"], s["matched"], s["hallucinations"]) == (4, 4, 3, 2)
    kinds = sorted((m["type"], m["why"]) for m in s["mistakes"])
    assert kinds == [("invented field", "owner Meera (key: UNKNOWN)"), ("invented item", "a suggestion, question or non-task")]
    total = gold.summarize([s])
    assert total["precision"] == 0.75 and total["recall"] == 0.75 and total["hallucination_rate"] == 0.5


def test_invented_deadline_and_lost_owner():
    g = GOLD["g04"]
    s = gold.score_note(g, [row("action", "Arun to update the onboarding deck.", "Arun", "Friday"),
                            row("action", "Meera will record the setup video by Oct 30.", "UNKNOWN", "Oct 30")])
    assert s["hallucinations"] == 1 and s["owners_lost"] == 1
    assert s["mistakes"][0]["why"] == "deadline Friday (key: none stated)"


G01_REPLY = {"meeting_topic": "Sprint 14", "decisions": [
    {"decision": "Ship mobile first", "owner": "UNKNOWN", "deadline": "UNKNOWN", "evidence_quote": "We agreed to ship mobile first.",
     "confidence": 0.9, "missing_info": []}], "contradictions": [],
    "actions": [
        {"id": "a1", "task": "Finish the API spec", "owner": "Priya", "deadline": "Nov 4", "dependencies": [],
         "evidence_quote": "Priya will finish the API spec by Nov 4.", "confidence": 0.9, "missing_info": []},
        {"id": "a2", "task": "Book offsite venue", "owner": "Arun", "deadline": "UNKNOWN", "dependencies": [],
         "evidence_quote": "Maybe look at offsite options, Arun?", "confidence": 0.5, "missing_info": []},
        {"id": "a3", "task": "Close the vendor renewal", "owner": "Meera", "deadline": "Nov 6", "dependencies": [],
         "evidence_quote": "Ask Meera whether someone can close the vendor renewal by Nov 6.", "confidence": 0.8, "missing_info": []}],
    "risks": [{"risk": "Staging too slow", "owner": "Ravi", "deadline": "UNKNOWN", "severity": "medium",
               "evidence_quote": "Ravi said the staging server might be too slow for load tests.", "confidence": 0.7, "missing_info": []}]}


def test_layers_show_each_check_removing_mistakes(settings_):
    """Pass 1 guesses three things; the code check fixes the reporter-owner, the Verifier drops the 'maybe'."""
    ai = ScriptedAI(settings_, [G01_REPLY])
    res = gold.evaluate(ai, [GOLD["g01"]])
    L = res["layers"]
    assert (L["pass1"]["hallucinations"], L["code"]["hallucinations"], L["full"]["hallucinations"]) == (3, 2, 1)
    assert L["full"]["recall"] == 1.0 and L["full"]["precision"] == 1.0
    note = res["per_note"][0]
    assert sorted(c["text"] for c in note["caught"]) == ["Book offsite venue", "Staging too slow"]
    assert [m["text"] for m in note["remaining"]] == ["Close the vendor renewal"]  # replay Verifier misses the asked-not-owner case


def test_failed_note_counts_as_nothing_found(settings_):
    res = gold.evaluate(ScriptedAI(settings_, ["nope", "nope"]), [GOLD["g06"]])
    assert res["failed_notes"] == ["g06"] and res["layers"]["full"]["recall"] == 0.0
    assert res["layers"]["full"]["precision"] is None


def test_scoreboard_reads_the_recorded_file(client, settings_, tmp_path, monkeypatch):
    res =gold.evaluate(ScriptedAI(settings_, [G01_REPLY]), [GOLD["g01"]])
    path = tmp_path / "results.json"
    path.write_text(json.dumps(res), encoding="utf-8")
    monkeypatch.setattr(gold, "RESULTS_FILE", path)
    a = client.get("/state", headers=MANAGER).json()["accuracy"]
    assert a["notes"] == 1 and a["layers"]["full"]["hallucinations"] == 1 and a["caught_total"] == 2
    assert "accuracy" not in client.get("/state", headers=as_user("raj@decisionos.demo")).json()
    monkeypatch.setattr(gold, "RESULTS_FILE", tmp_path / "missing.json")
    assert client.get("/state", headers=MANAGER).json()["accuracy"] is None


def test_purge_removes_a_meeting_and_everything_from_it(client):
    m0 = extract(client, "demo_meeting_0", "2026-10-19")["meeting_id"]
    m1 = extract(client, "demo_meeting_1", "2026-10-26")["meeting_id"]
    st = client.get("/state", headers=MANAGER).json()
    assert any(c["source"] == "cross_meeting" for c in st["conflicts"])
    assert client.delete(f"/meetings/{m0}", headers=as_user("raj@decisionos.demo")).status_code == 403
    r = client.delete(f"/meetings/{m0}", headers=MANAGER)
    assert r.status_code == 200 and r.json()["items"] == 5
    st = client.get("/state", headers=MANAGER).json()
    assert [m["id"] for m in st["meetings"]] == [m1]
    assert all(i["meeting_id"] == m1 for i in st["actions"] + st["decisions"] + st["risks"])
    assert all(c["meeting_id"] == m1 and c["source"] != "cross_meeting" for c in st["conflicts"])
    assert client.get(f"/meetings/{m0}/source", headers=MANAGER).status_code == 404
    assert client.delete(f"/meetings/{m0}", headers=MANAGER).status_code == 404
    assert st["ai_calls"]  # the audit log keeps its rows


def test_evidence_fingerprint_stored_and_exported(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    a = st["actions"][0]
    assert a["evidence_hash"] == evidence_hash(a["evidence_quote"]) and len(a["evidence_hash"]) == 16
    assert a["evidence_hash"] in client.get("/export.csv", headers=MANAGER).text


def test_demo_meeting_shows_the_verifier_removing_a_suggestion(client):
    out = extract(client)
    assert out["items"] == 5 and out["verify"]["removed"] == 1
    gone = next(r for r in out["rejected"] if r["by"] == "verifier")
    assert gone["text"] == "Book offsite venue for the launch party"
