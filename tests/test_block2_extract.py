"""Block 2: POST /extract returns validated data, persists it, and never guesses."""

from app.qualcomm import QualcommError

from conftest import MANAGER, ScriptedAI, as_user, extract, make_client, notes


def test_extract_persists_and_returns(client):
    out = extract(client)
    assert out["items"] == 5 and out["topic"] == "Checkout release"
    st = client.get("/state", headers=MANAGER).json()
    tasks = {a["ref"]: a for a in st["actions"]}
    assert tasks["a1"]["owner"] == "Raj" and tasks["a1"]["team"] == "Platform"
    assert tasks["a2"]["owner"] == "Priya" and tasks["a2"]["depends_on"] == [tasks["a1"]["id"]]


def test_refuses_to_guess_owner(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    follow = next(a for a in st["actions"] if "finance" in a["text"].lower())
    assert follow["owner"] is None and "owner" in follow["missing_info"]
    assert any("not named in the source sentence" in c for c in follow["checks"])
    assert follow["id"] in {i["id"] for i in st["needs_review"]}
    assert st["stats"]["unassigned_actions"] >= 1


def test_relative_deadline_needs_confirmation(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    raj = next(a for a in st["actions"] if a["owner"] == "Raj")
    assert raj["deadline_date"] == "2026-10-30" and raj["deadline_status"] == "needs_confirmation"
    assert "deadline_confirmation" in raj["missing_info"]
    assert "needs confirmation" in raj["deadline_text"]


def test_evidence_offsets_point_at_the_sentence(client):
    out = extract(client)
    st = client.get("/state", headers=MANAGER).json()
    src = client.get(f"/meetings/{out['meeting_id']}/source", headers=MANAGER).json()["notes"]
    for a in st["actions"] + st["risks"] + st["decisions"]:
        assert a["evidence_quote"].rstrip(".") in src[a["ev_start"]:a["ev_end"]]


def test_in_meeting_contradiction_stored(client):
    extract(client)
    conflicts = client.get("/state", headers=MANAGER).json()["conflicts"]
    assert any(c["current"] == "AWS" and c["previous"] == "Azure" for c in conflicts)


GOOD = {"meeting_topic": "Ops", "decisions": [], "risks": [], "contradictions": [], "actions": [
    {"id": "a1", "task": "Fix login", "owner": "Raj", "deadline": "tomorrow", "dependencies": [],
     "evidence_quote": "Raj will fix the login bug tomorrow.", "confidence": 0.9, "missing_info": []}]}
NOTES = "Ops sync. Raj will fix the login bug tomorrow."


def post(c):
    return c.post("/extract", json={"notes": NOTES, "meeting_date": "2026-10-26"}, headers=MANAGER)


def test_invalid_json_retries_once_then_succeeds(settings_, db):
    ai = ScriptedAI(settings_, ["Sure! here are the items", GOOD])
    r = post(make_client(settings_, db, ai))
    assert r.status_code == 200 and r.json()["attempts"] == 2 and ai.calls == 2


def test_two_failures_save_nothing(settings_, db):
    ai = ScriptedAI(settings_, ["nope", "still nope"])
    c = make_client(settings_, db, ai)
    r = post(c)
    assert r.status_code == 502 and r.json()["code"] == "INVALID_AI_RESPONSE" and ai.calls == 2
    assert c.get("/state", headers=MANAGER).json()["actions"] == []


def test_invented_quote_is_repaired_or_rejected(settings_, db):
    bad = {**GOOD, "actions": [{**GOOD["actions"][0], "evidence_quote": "Raj promised to fix everything."}]}
    ai = ScriptedAI(settings_, [bad, bad])
    r = post(make_client(settings_, db, ai))
    assert r.status_code == 200 and ai.calls == 2
    assert r.json()["items"] == 0 and r.json()["rejected"][0]["reason"].startswith("Evidence sentence not found")


def test_invented_deadline_becomes_unknown(settings_, db):
    bad = {**GOOD, "actions": [{**GOOD["actions"][0], "deadline": "Oct 31"}]}
    c = make_client(settings_, db, ScriptedAI(settings_, [bad]))
    post(c)
    a = c.get("/state", headers=MANAGER).json()["actions"][0]
    assert a["deadline_raw"] == "UNKNOWN" and "deadline" in a["missing_info"]


def test_transient_error_uses_the_retry(settings_, db):
    ai = ScriptedAI(settings_, [QualcommError("TIMEOUT", "slow", True), GOOD])
    assert post(make_client(settings_, db, ai)).status_code == 200 and ai.calls == 2


def test_auth_error_not_retried(settings_, db):
    ai = ScriptedAI(settings_, [QualcommError("AUTH", "bad key", False)])
    r = post(make_client(settings_, db, ai))
    assert r.status_code == 502 and r.json()["code"] == "AUTH" and ai.calls == 1


def test_requires_internal_token_and_manager(client):
    assert client.post("/extract", json={"notes": "x", "meeting_date": "2026-10-26"}).status_code == 401
    bad = {"x-internal-token": "wrong", "x-user-email": "vishal@decisionos.demo"}
    assert client.get("/state", headers=bad).status_code == 401
    r = client.post("/extract", json={"notes": notes("demo_meeting_1"), "meeting_date": "2026-10-26"},
                    headers=as_user("raj@decisionos.demo"))
    assert r.status_code == 403


def test_state_polling_reports_no_change(client):
    v = client.get("/state", headers=MANAGER).json()["version"]
    assert client.get(f"/state?since={v}", headers=MANAGER).json() == {"changed": False, "version": v}


def test_highlight_is_exactly_one_sentence(client):
    out = extract(client)
    st = client.get("/state", headers=MANAGER).json()
    src = client.get(f"/meetings/{out['meeting_id']}/source", headers=MANAGER).json()["notes"]
    raj = next(a for a in st["actions"] if a["owner"] == "Raj")
    assert src[raj["ev_start"]:raj["ev_end"]] == "Monday project meeting: Raj said the payment API will be ready by Friday."
    priya = next(a for a in st["actions"] if a["owner"] == "Priya")
    assert src[priya["ev_start"]:priya["ev_end"]] == "Priya will test it once Raj finishes."
