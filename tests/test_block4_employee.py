"""Block 4: employee sees only their tasks; status changes flow to the manager view."""

from conftest import MANAGER, as_user, extract

RAJ = as_user("raj@decisionos.demo")
PRIYA = as_user("priya@decisionos.demo")


def mgr(c):
    return c.get("/state", headers=MANAGER).json()


def task(st, owner):
    return next(a for a in st["actions"] if a["owner"] == owner)


def test_employee_sees_only_own_tasks_with_dependencies(client):
    extract(client)
    me = client.get("/state", headers=PRIYA).json()
    assert me["me"]["role"] == "employee" and "graph" not in me
    assert [t["text"] for t in me["tasks"]] == ["Test payment API"]
    assert me["tasks"][0]["blocked_by"][0]["owner"] == "Raj"
    raj = client.get("/state", headers=RAJ).json()
    assert raj["tasks"][0]["blocking"][0]["owner"] == "Priya"


def test_status_change_updates_manager_view(client):
    extract(client)
    raj_task = task(mgr(client), "Raj")
    v = mgr(client)["version"]
    r = client.patch(f"/items/{raj_task['id']}/status", json={"status": "in_progress"}, headers=RAJ)
    assert r.status_code == 200
    poll = client.get(f"/state?since={v}", headers=MANAGER).json()
    assert poll["changed"] is True and task(poll, "Raj")["status"] == "in_progress"


def test_mark_blocked_turns_red_and_cascades(client):
    extract(client)
    raj_task = task(mgr(client), "Raj")
    client.patch(f"/items/{raj_task['id']}/status", json={"status": "blocked", "reason": "Waiting on API contract"}, headers=RAJ)
    st = mgr(client)
    assert task(st, "Raj")["color"] == "red"
    assert task(st, "Priya")["at_risk"] is True and task(st, "Priya")["color"] == "orange"
    assert st["stats"]["blocked_handoffs"] == 1
    assert any(e["blocked"] for e in st["graph"]["edges"])
    assert any("blocked" in n["text"] and "Waiting on API contract" in n["text"] for n in st["notifications"])
    priya = client.get("/state", headers=PRIYA).json()
    assert any(n["kind"] == "upstream_blocked" for n in priya["notifications"])
    assert "blocked" in st["callout"]["text"]


def test_done_unblocks_downstream_owner(client):
    extract(client)
    raj_task = task(mgr(client), "Raj")
    client.patch(f"/items/{raj_task['id']}/status", json={"status": "blocked"}, headers=RAJ)
    client.patch(f"/items/{raj_task['id']}/status", json={"status": "done"}, headers=RAJ)
    st = mgr(client)
    assert task(st, "Raj")["color"] == "green" and task(st, "Priya")["at_risk"] is False
    priya = client.get("/state", headers=PRIYA).json()
    assert any(n["kind"] == "unblocked" and "You can start" in n["text"] for n in priya["notifications"])
    assert priya["unread"] >= 1
    client.post("/notifications/read", headers=PRIYA)
    assert client.get("/state", headers=PRIYA).json()["unread"] == 0


def test_cannot_update_someone_elses_task(client):
    extract(client)
    raj_task = task(mgr(client), "Raj")
    assert client.patch(f"/items/{raj_task['id']}/status", json={"status": "done"}, headers=PRIYA).status_code == 403
    assert client.patch(f"/items/{raj_task['id']}/status", json={"status": "finished"}, headers=RAJ).status_code == 422
    assert client.patch(f"/items/{raj_task['id']}/status", json={"status": "done"}, headers=MANAGER).status_code == 200
