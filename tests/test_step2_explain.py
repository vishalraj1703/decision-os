"""Step 2: Health Score, slack-based delay propagation (what-if), Clarify Loop, export."""

import csv
import io

from app import health, risk

from conftest import MANAGER, as_user, extract


def task(id_, team, due, deps=(), status="not_started", slack_days=None):
    return {"id": id_, "text": f"Task {id_}", "owner": team, "team": team, "deadline_date": due, "depends_on": list(deps),
            "status": status, "slack_days": slack_days}


# The documentation's example: Design slips 5 days; Frontend has 5 days of slack; QA has none.
PDF_GRAPH = [
    task("design", "Design", "2026-10-30"),
    task("frontend", "Frontend", "2026-11-05", ["design"]),   # 6 days after design, minus 1 day of work = 5
    task("qa", "QA", "2026-10-31", ["design"]),               # 1 day after design = no slack
    task("release", None, None, ["qa"]),                      # no date of its own: follows QA directly
]


def test_slack_comes_from_the_deadlines():
    s = risk.slack(PDF_GRAPH)
    assert s["design"]["days"] == 0 and s["design"]["source"] == "none"
    assert s["frontend"]["days"] == 5 and s["qa"]["days"] == 0 and s["release"]["days"] == 0


def test_documented_example_two_teams_five_days():
    r = risk.propagate(PDF_GRAPH, "design", 5)
    assert r["delays"] == {"design": 5, "qa": 5, "release": 5}
    assert r["absorbed"] == {"frontend": 5}
    assert r["teams"] == ["Design", "QA"] and r["teams_affected"] == 2 and r["days_at_risk"] == 5
    assert r["sentence"] == "Design slips 5 days: 2 downstream tasks late, 2 teams (+1 with no owner), 5 days at risk."


def test_bigger_slip_breaks_through_slack():
    r = risk.propagate(PDF_GRAPH, "design", 7)
    assert r["delays"]["frontend"] == 2 and r["teams_affected"] == 3


def test_manual_slack_done_tasks_and_cycles():
    g = [task("a", "A", "2026-10-30"), task("b", "B", "2026-10-31", ["a"], slack_days=3),
         task("c", "C", None, ["b"]), task("d", "D", None, ["a"], status="done")]
    r = risk.propagate(g, "a", 2)
    assert r["delays"] == {"a": 2} and r["absorbed"] == {"b": 2, "d": 2}
    loop = [task("x", "X", None, ["y"]), task("y", "Y", None, ["x"]), task("z", "Z", None)]
    assert risk.propagate(loop, "z", 3)["delays"] == {"z": 3}  # cycle skipped, no hang


def item(kind, owner="Raj", exact=True, conf=0.88, flags=(), supported=True, iid=None):
    return {"id": iid or f"{kind}-{id(flags)}-{owner}-{conf}", "kind": kind, "owner": owner, "status": "not_started",
            "deadline_date": "2026-11-01" if exact else None, "deadline_status": "exact" if exact else "unknown",
            "confidence": conf, "missing_info": list(flags), "review_state": "ok",
            "verification": {"supported": supported}}


def test_health_formula_matches_hand_calculation():
    tasks = [item("action", owner="Raj" if n < 7 else None, exact=n < 5,
                  flags=(["owner"] if n >= 7 else []) + (["deadline"] if n >= 5 else []), iid=f"t{n}") for n in range(10)]
    decisions = [item("decision", owner=None, exact=False, iid=f"d{n}") for n in range(4)]
    conflicts = [{"status": "open", "current_item_id": "d0"}, {"status": "confirmed_current", "current_item_id": "d1"}]
    h = health.score(tasks + decisions, conflicts)
    parts = {p["key"]: p for p in h["parts"]}
    assert parts["O"]["detail"] == "7 of 10" and parts["O"]["points"] == 21.0
    assert parts["D"]["detail"] == "5 of 10" and parts["D"]["points"] == 12.5
    assert parts["V"]["points"] == 17.6
    assert parts["A"]["detail"] == "5 of 14 flagged" and parts["A"]["points"] == round(15 * (1 - 5 / 14), 1)
    assert parts["C"]["detail"] == "1 of 4 in conflict" and parts["C"]["points"] == 7.5
    expected = 21 + 12.5 + 17.6 + 15 * (1 - 5 / 14) + 7.5
    assert h["score"] == round(expected) and abs(h["lost"] - round(100 - expected, 1)) < 0.05


def test_health_rises_when_the_manager_fixes_a_gap(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    before = st["health"]["score"]
    follow = next(a for a in st["actions"] if "finance" in a["text"].lower())
    client.post(f"/items/{follow['id']}/resolve", json={"action": "assign_owner", "value": "kavya@decisionos.demo"}, headers=MANAGER)
    after = client.get("/state", headers=MANAGER).json()["health"]
    assert after["score"] > before and next(p for p in after["parts"] if p["key"] == "O")["detail"] == "3 of 3"


def test_whatif_endpoint_and_slack_override(client):
    extract(client, "demo_meeting_0", "2026-10-19")
    st = client.get("/state", headers=MANAGER).json()
    by = {a["owner"]: a for a in st["actions"]}
    assert by["Asha"]["slack"]["days"] == 0
    w = client.get(f"/whatif/{by['Ravi']['id']}", headers=MANAGER).json()
    assert len(w["steps"]) == 11 and w["steps"][0]["delays"] == {}
    three = w["steps"][3]
    assert three["delays"] == {by["Ravi"]["id"]: 3, by["Asha"]["id"]: 3, by["Meera"]["id"]: 3}
    assert three["teams"] == ["Platform", "Product", "Quality"]
    assert client.patch(f"/items/{by['Asha']['id']}/slack", json={"days": 5}, headers=MANAGER).status_code == 200
    three = client.get(f"/whatif/{by['Ravi']['id']}", headers=MANAGER).json()["steps"][3]
    assert three["delays"] == {by["Ravi"]["id"]: 3} and by["Asha"]["id"] in three["absorbed"]
    assert client.get(f"/whatif/{by['Ravi']['id']}", headers=as_user("raj@decisionos.demo")).status_code == 403
    assert client.patch(f"/items/{by['Asha']['id']}/slack", json={"days": 99}, headers=MANAGER).status_code == 422


def test_clarify_drafts_go_to_the_right_person(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    review = {i["text"]: i for i in st["needs_review"]}
    follow = review["Follow up with finance on the hosting budget"]
    q = next(d for d in follow["clarify"] if d["flag"] == "owner")
    assert [p["name"] for p in q["to"]] == ["Kavya"] and q["why"] == "Finance team"
    assert q["question"].startswith("Who owns the task “Follow up with finance")
    raj = review["Build payment API"]
    q = next(d for d in raj["clarify"] if d["flag"] == "deadline_confirmation")
    assert [p["name"] for p in q["to"]] == ["Raj"] and "“Friday”" in q["question"] and "Fri 30 Oct" in q["question"]


def test_clarify_send_notifies_once(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    follow = next(i for i in st["needs_review"] if "finance" in i["text"].lower())
    body = {"flag": "owner", "to": "kavya@decisionos.demo", "question": "Who owns the finance follow-up?"}
    r = client.post(f"/items/{follow['id']}/clarify", json=body, headers=MANAGER)
    assert r.status_code == 200 and r.json()["to"] == "Kavya" and r.json()["email_status"] == "skipped"
    assert client.post(f"/items/{follow['id']}/clarify", json=body, headers=MANAGER).status_code == 409
    kavya = client.get("/state", headers=as_user("kavya@decisionos.demo")).json()
    assert any(n["text"] == "Vishal asks: Who owns the finance follow-up?" for n in kavya["notifications"])
    st = client.get("/state", headers=MANAGER).json()
    assert next(i for i in st["needs_review"] if i["id"] == follow["id"])["clarify_sent"][0]["to"] == "Kavya"
    bad = client.post(f"/items/{follow['id']}/clarify", json={**body, "flag": "deadline_confirmation"}, headers=MANAGER)
    assert bad.status_code == 422
    assert client.post(f"/items/{follow['id']}/clarify", json=body, headers=as_user("raj@decisionos.demo")).status_code == 403


def test_csv_export(client):
    extract(client)
    r = client.get("/export.csv", headers=MANAGER)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 3
    follow = next(x for x in rows if "finance" in x["Task"].lower())
    assert follow["Owner"] == "UNKNOWN" and "owner" in follow["Flags"] and follow["Verified"] == "yes"
    priya = next(x for x in rows if x["Owner"] == "Priya")
    assert priya["Depends on"] == "Build payment API"
    assert client.get("/export.csv", headers=as_user("raj@decisionos.demo")).status_code == 403


def test_csv_blocks_formula_cells():
    from app.export import _cell
    assert _cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")" and _cell("Fix login") == "Fix login"


def test_jira_export(client):
    extract(client)
    issues = client.get("/export/jira.json?project=ops-1", headers=MANAGER).json()["issueUpdates"]
    assert len(issues) == 3 and all(i["fields"]["project"] == {"key": "OPS1"} for i in issues)
    raj = next(i["fields"] for i in issues if "owner-raj" in i["fields"]["labels"])
    assert "duedate" not in raj and "missing-deadline-confirmation" in raj["labels"]  # Friday is not confirmed yet
    assert "{quote}" in raj["description"]
