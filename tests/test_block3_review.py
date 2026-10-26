"""Block 3: Needs Review queue resolves gaps; dashboard state has stats, graph and strip."""

from conftest import MANAGER, as_user, extract


def state(c):
    return c.get("/state", headers=MANAGER).json()


def finance(st):
    return next(a for a in st["actions"] if "finance" in a["text"].lower())


def test_manager_state_shape(client):
    extract(client, "demo_meeting_0", "2026-10-19")
    st = state(client)
    assert st["stats"]["teams_in_scope"] == 3  # Platform, Product, Quality
    assert len(st["graph"]["nodes"]) == 3 and len(st["graph"]["edges"]) == 2
    assert {t["team"] for t in st["teams"]} == {"Platform", "Product", "Quality"}
    assert st["callout"]["text"]


def test_assign_owner_clears_review_and_notifies(client):
    extract(client)
    item = finance(state(client))
    r = client.post(f"/items/{item['id']}/resolve", json={"action": "assign_owner", "value": "kavya@decisionos.demo"}, headers=MANAGER)
    assert r.status_code == 200
    st = state(client)
    item = finance(st)
    assert item["owner"] == "Kavya" and item["team"] == "Finance" and "owner" not in item["missing_info"]
    me = client.get("/state", headers=as_user("kavya@decisionos.demo")).json()
    assert [t["id"] for t in me["tasks"]] == [item["id"]]
    assert any("assigned" in n["kind"] for n in me["notifications"])


def test_set_deadline_and_confirm(client):
    extract(client)
    st = state(client)
    item = finance(st)
    client.post(f"/items/{item['id']}/resolve", json={"action": "set_deadline", "value": "2026-10-29"}, headers=MANAGER)
    assert finance(state(client))["deadline_date"] == "2026-10-29"
    raj = next(a for a in st["actions"] if a["owner"] == "Raj")
    client.post(f"/items/{raj['id']}/resolve", json={"action": "confirm_deadline"}, headers=MANAGER)
    raj = next(a for a in state(client)["actions"] if a["owner"] == "Raj")
    assert raj["deadline_status"] == "exact" and raj["missing_info"] == [] and raj["review_state"] == "ok"


def test_discard_and_follow_up(client):
    extract(client)
    item = finance(state(client))
    client.post(f"/items/{item['id']}/resolve", json={"action": "follow_up"}, headers=MANAGER)
    assert finance(state(client))["review_state"] == "follow_up"
    client.post(f"/items/{item['id']}/resolve", json={"action": "discard"}, headers=MANAGER)
    assert all("finance" not in a["text"].lower() for a in state(client)["actions"])


def test_employee_cannot_resolve_and_bad_owner_rejected(client):
    extract(client)
    item = finance(state(client))
    assert client.post(f"/items/{item['id']}/resolve", json={"action": "discard"},
                       headers=as_user("raj@decisionos.demo")).status_code == 403
    assert client.post(f"/items/{item['id']}/resolve", json={"action": "assign_owner", "value": "Bob"},
                       headers=MANAGER).status_code == 422
