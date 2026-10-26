"""Block 6: a passed deadline marks the task overdue and walks the dependency chain."""

import datetime as dt

from app import cascade

from conftest import MANAGER, as_user, extract


def seed(c):
    extract(c, "demo_meeting_0", "2026-10-19")  # Ravi (Oct 27) -> Asha (Oct 28) -> Meera (Oct 29)


def st(c):
    return c.get("/state", headers=MANAGER).json()


def by_owner(s, owner):
    return next(a for a in s["actions"] if a["owner"] == owner)


def test_overdue_cascades_downstream(client):
    seed(client)
    r = client.post("/admin/clock", json={"date": "2026-10-28"}, headers=MANAGER).json()
    assert r["today"] == "2026-10-28" and r["newly_overdue"] == ["Approve the API contract"]
    s = st(client)
    ravi, asha, meera = by_owner(s, "Ravi"), by_owner(s, "Asha"), by_owner(s, "Meera")
    assert ravi["overdue"] and ravi["color"] == "red"
    assert asha["at_risk"] and asha["color"] == "orange"
    assert meera["at_risk"] and meera["color"] == "orange"  # transitive
    assert s["stats"]["blocked_handoffs"] == 1 and s["simulated"] is True
    assert {t["team"]: t["color"] for t in s["teams"]}["Platform"] == "red"
    bell = [n["text"] for n in s["notifications"]]
    assert any("Ravi's 'Approve the API contract' is overdue" in t and "Asha's Build the checkout flow" in t for t in bell)
    asha_view = client.get("/state", headers=as_user("asha@decisionos.demo")).json()
    assert any(n["kind"] == "at_risk" for n in asha_view["notifications"])


def test_check_is_idempotent(client):
    seed(client)
    client.post("/admin/clock", json={"date": "2026-10-28"}, headers=MANAGER)
    n1 = len(st(client)["notifications"])
    r = client.post("/admin/run-check", headers=MANAGER).json()
    assert r["newly_overdue"] == [] and len(st(client)["notifications"]) == n1


def test_done_clears_the_cascade(client):
    seed(client)
    client.post("/admin/clock", json={"date": "2026-10-28"}, headers=MANAGER)
    ravi = by_owner(st(client), "Ravi")
    client.patch(f"/items/{ravi['id']}/status", json={"status": "done"}, headers=as_user("ravi@decisionos.demo"))
    s = st(client)
    assert by_owner(s, "Ravi")["color"] == "green" and not by_owner(s, "Asha")["at_risk"]
    assert s["stats"]["blocked_handoffs"] == 0


def test_back_to_real_time(client):
    seed(client)
    client.post("/admin/clock", json={"date": "2026-10-28"}, headers=MANAGER)
    client.post("/admin/clock", json={"date": None}, headers=MANAGER)
    assert st(client)["simulated"] is False


def test_employee_cannot_move_the_clock(client):
    assert client.post("/admin/clock", json={"date": "2026-10-28"}, headers=as_user("raj@decisionos.demo")).status_code == 403


def test_compute_pure():
    items = [
        {"id": "a", "kind": "action", "review_state": "ok", "deadline_date": "2026-10-27", "status": "in_progress", "depends_on": []},
        {"id": "b", "kind": "action", "review_state": "ok", "deadline_date": None, "status": "not_started", "depends_on": ["a"]},
        {"id": "c", "kind": "action", "review_state": "ok", "deadline_date": "2026-10-20", "status": "done", "depends_on": []},
    ]
    flags = cascade.compute(items, dt.date(2026, 10, 28))
    assert flags == {"a": (True, False), "b": (False, True), "c": (False, False)}
