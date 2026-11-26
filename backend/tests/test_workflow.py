"""API tests for the downtime rules.

By default they use an in-memory MongoDB substitute. To run against a real server:
    TEST_MONGO_URL=mongodb://localhost:27017 pytest
(a database named smt6_test is DROPPED first).
"""
import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

os.environ.update(MONGO_URL=os.getenv("TEST_MONGO_URL", "memory://"), MONGO_DB="smt6_test",
                  SEED_DEMO="false", ADMIN_PASSWORD="Admin-Pass-123")

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import config, security
from app.main import app
from app.util import now

M = "SMT6-0014"
PW = "Test-Pass-123"


@pytest.fixture
def api():
    if not config.MONGO_URL.startswith("memory://"):
        from pymongo import MongoClient
        MongoClient(config.MONGO_URL).drop_database(config.MONGO_DB)
    security._failures.clear()
    with TestClient(app) as c:
        def login(name, password):
            r = c.post("/api/auth/login", json={"username": name, "password": password})
            assert r.status_code == 200, r.text
            return {"Authorization": f"Bearer {r.json()['token']}"}
        admin = login("admin", "Admin-Pass-123")
        c.h = {"admin": admin}
        for role in ("operator", "technician", "supervisor"):
            assert c.post("/api/users", headers=admin, json={
                "username": role, "full_name": role.title(), "role": role, "password": PW}).status_code == 201
            c.h[role] = login(role, PW)
        yield c


def status(c, value, who="operator", machine=M, **extra):
    return c.post(f"/api/control/machines/{machine}/status", headers=c.h[who], json={"status": value, **extra})


def down(c, **extra):
    r = status(c, "DOWN", problem={"description": "Feeder jam", "category": "Feeder"}, **extra)
    assert r.status_code == 200, r.text
    return r.json()["event"]


def recover(c, event_id, **extra):
    return c.post(f"/api/events/{event_id}/recovery", headers=c.h["operator"],
                  json={"production_confirmed": True, "verification_note": "Good boards verified", **extra})


def card(c, machine=M):
    return next(m for m in c.get("/api/public/dashboard").json()["machines"] if m["id"] == machine)


def count(c):
    return c.get("/api/history/events", headers=c.h["admin"]).json()["total"]


def test_four_machines_public_and_view_only(api):
    ids = [m["id"] for m in api.get("/api/public/dashboard").json()["machines"]]
    assert ids == ["SMT6-0014", "SMT6-0015", "SMT6-0044", "SMT6-0052"]
    assert api.post(f"/api/control/machines/{M}/status", json={"status": "RUNNING"}).status_code == 401
    assert api.get("/api/history/events").status_code == 401


def test_one_breakdown_is_one_event_through_all_statuses(api):
    event = down(api)
    start = event["started_at"]
    for value in ("TESTING/RECOVERY", "DOWN", "SETUP", "IDLE", "TESTING/RECOVERY"):
        r = status(api, value)
        assert r.status_code == 200, r.text
        assert r.json()["event"]["state"] == "OPEN" and r.json()["event"]["started_at"] == start
    assert status(api, "RUNNING").status_code == 409                     # cannot bypass confirmation
    assert status(api, "DOWN", problem={"description": "Second"}).status_code == 409
    r = api.post(f"/api/events/{event['id']}/problems", headers=api.h["technician"],
                 json={"description": "Nozzle alarm", "category": "Nozzle / Head"})
    assert len(r.json()["problems"]) == 2 and count(api) == 1
    assert card(api)["status"] == "TESTING/RECOVERY" and card(api)["event"]["started_at"] == start


def test_recovery_requires_confirmation_then_new_breakdown_is_new_event(api):
    first = down(api)
    assert recover(api, first["id"], production_confirmed=False).status_code == 422
    assert recover(api, first["id"], verification_note="   ").status_code == 422
    closed = recover(api, first["id"]).json()
    assert closed["state"] == "CLOSED" and closed["recovery"]["confirmed_by"]["username"] == "operator"
    assert card(api)["status"] == "RUNNING" and card(api)["event"] is None
    assert recover(api, first["id"]).status_code == 409
    second = down(api)
    assert second["id"] != first["id"] and second["event_no"] != first["event_no"] and count(api) == 2


def test_simultaneous_down_reports_create_one_event(api):
    with ThreadPoolExecutor(6) as pool:
        codes = [r.status_code for r in pool.map(
            lambda _: status(api, "DOWN", problem={"description": "Jam"}), range(6))]
    assert count(api) == 1 and codes.count(200) == 1, codes


def test_database_rejects_second_open_event(api):
    from pymongo.errors import DuplicateKeyError
    from app import db
    down(api)

    async def insert():
        await db.db.downtime_events.insert_one({"_id": "x", "event_no": "x", "open_key": M, "machine_id": M})
    with pytest.raises(DuplicateKeyError):
        api.portal.call(insert)


def test_backdating_limits_and_duration(api):
    started = (now() - timedelta(hours=2)).isoformat()
    event = down(api, occurred_at=started)
    assert 7195 <= event["duration_seconds"] <= 7210
    assert recover(api, event["id"], recovered_at=(now() - timedelta(hours=3)).isoformat()).status_code == 422
    assert recover(api, event["id"], recovered_at=(now() + timedelta(hours=1)).isoformat()).status_code == 422
    assert recover(api, event["id"]).status_code == 200
    r = status(api, "DOWN", problem={"description": "Again"}, occurred_at=(now() - timedelta(hours=1)).isoformat())
    assert r.status_code == 422                                           # would overlap the previous event
    r = status(api, "DOWN", problem={"description": "Naive"}, occurred_at="2026-01-01T10:00:00")
    assert r.status_code == 422                                           # time zone is mandatory


def test_problem_work_attendance_and_closed_amendments(api):
    event = down(api)
    eid, pid = event["id"], event["problems"][0]["id"]
    base, tech = f"/api/events/{eid}", api.h["technician"]
    assert api.post(f"{base}/problems", headers=api.h["operator"], json={"description": "x"}).status_code == 403
    r = api.patch(f"{base}/problems/{pid}", headers=tech, json={"root_cause": "Worn sprocket", "status": "RESOLVED", "expected_revision": 1})
    assert r.json()["problems"][0]["resolved_at"]
    stale = api.patch(f"{base}/problems/{pid}", headers=tech,
                      json={"root_cause": "other", "expected_revision": 1})
    assert stale.status_code == 409
    assert api.post(f"{base}/problems/{pid}/actions", headers=tech,
                    json={"type": "CORRECTIVE", "description": "Replaced"}).status_code == 200
    part = {"part_name": "Sprocket", "source": "DONOR_MACHINE"}
    assert api.post(f"{base}/problems/{pid}/parts", headers=tech, json=part).status_code == 422
    assert api.post(f"{base}/problems/{pid}/parts", headers=tech,
                    json={**part, "donor_machine": "SMT6-0052"}).status_code == 200
    r = api.post(f"{base}/attendance", headers=tech, json={})
    first = r.json()["attendance"][0]
    assert first["technician_name"] == "Technician"
    assert api.post(f"{base}/attendance", headers=tech, json={}).status_code == 409
    assert api.post(f"{base}/attendance/{first['id']}/checkout", headers=tech, json={}).status_code == 200
    api.post(f"{base}/attendance", headers=tech, json={"technician_name": "Second Tech"})
    assert card(api)["event"]["technicians"] == ["Second Tech"]
    closed = recover(api, eid).json()
    assert all(a["left_at"] for a in closed["attendance"]) and closed["attendance"][1]["auto_checkout"]
    assert api.post(f"{base}/problems", headers=tech, json={"description": "late"}).status_code == 409
    assert api.patch(f"{base}/problems/{pid}", headers=tech, json={"root_cause": "late", "expected_revision": 2}).status_code == 403
    r = api.patch(f"{base}/problems/{pid}", headers=api.h["supervisor"], json={"root_cause": "Confirmed cause", "expected_revision": 2})
    assert r.status_code == 200 and r.json()["state"] == "CLOSED" and r.json()["recovered_at"] == closed["recovered_at"]
    logs = api.get("/api/audit", headers=api.h["supervisor"], params={"event_no": event["event_no"]}).json()["items"]
    amended = next(a for a in logs if a["details"].get("amended_after_close"))
    assert amended["details"]["before"]["root_cause"] == "Worn sprocket"
    assert {"event.opened", "event.closed", "part.added", "attendance.check_in"} <= {a["action"] for a in logs}


def test_no_delete_routes_and_roles(api):
    assert not [r for r in app.routes if "DELETE" in (getattr(r, "methods", None) or set())]
    assert api.get("/api/audit", headers=api.h["technician"]).status_code == 403
    assert api.get("/api/users", headers=api.h["supervisor"]).status_code == 403
    users = api.get("/api/users", headers=api.h["admin"]).json()
    assert all("password_hash" not in u for u in users)
    op = next(u for u in users if u["username"] == "operator")
    api.patch(f"/api/users/{op['id']}", headers=api.h["admin"], json={"active": False})
    assert status(api, "SETUP").status_code == 401                        # existing session revoked
    me = next(u for u in users if u["username"] == "admin")
    assert api.patch(f"/api/users/{me['id']}", headers=api.h["admin"], json={"active": False}).status_code == 409


def test_login_rate_limit(api):
    codes = [api.post("/api/auth/login", json={"username": "supervisor", "password": "bad"}).status_code
             for _ in range(10)]
    assert codes[0] == 401 and codes[-1] == 429


def test_websocket_pushes_updates(api):
    with api.websocket_connect("/ws/dashboard") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        down(api)
        machine = ws.receive_json()["machines"][0]
        assert machine["status"] == "DOWN" and machine["event"]["problems"][0]["description"] == "Feeder jam"
        assert "created_by" not in machine["event"]


def test_filters_summary_and_exports(api):
    event = down(api)
    api.post(f"/api/events/{event['id']}/problems", headers=api.h["technician"],
             json={"description": '=HYPERLINK("bad")', "category": "Software / Program"})
    get = lambda **p: api.get("/api/history/events", headers=api.h["operator"], params=p).json()
    today = now().astimezone(config.PLANT_TZ).date()
    assert get(machine=M, state="OPEN", q="feeder", date_from=today, date_to=today)["total"] == 1
    assert get(machine="SMT6-0015")["total"] == 0 and get(state="CLOSED")["total"] == 0
    assert get(date_to=today - timedelta(days=1))["total"] == 0
    assert get(q=".*(")["total"] == 0 and get(category="Feeder")["total"] == 1
    assert get()["summary"]["by_machine"][0]["breakdowns"] == 1
    csv = api.get("/api/history/export.csv", headers=api.h["operator"]).content.decode("utf-8-sig")
    assert event["event_no"] in csv
    xlsx = api.get("/api/history/export.xlsx", headers=api.h["operator"]).content
    wb = load_workbook(io.BytesIO(xlsx))
    assert wb.sheetnames == ["Events", "Problems", "Actions", "Parts", "Attendance"]
    assert wb["Problems"]["C3"].value.startswith("'=") and wb["Problems"]["C3"].data_type == "s"


def test_actions_do_not_block_an_edit_and_users_are_attributed(api):
    event = down(api)
    base = f"/api/events/{event['id']}/problems/{event['problems'][0]['id']}"
    tech = api.h["technician"]
    api.post(f"{base}/actions", headers=tech, json={"type": "TROUBLESHOOTING", "description": "Checked"})
    assert api.patch(base, headers=tech, json={"root_cause": "Jam", "expected_revision": 1}).status_code == 200
    users = api.get("/api/users", headers=api.h["admin"]).json()
    op = next(u for u in users if u["username"] == "operator")
    assert op["created_by"]["username"] == "admin"
    r = api.patch(f"/api/users/{op['id']}", headers=api.h["admin"], json={"full_name": "Line Operator"})
    assert r.json()["updated_by"]["username"] == "admin"
    r = api.post("/api/users", headers=api.h["admin"], json={
        "username": "longpw", "full_name": "x", "role": "operator", "password": "\u00e9" * 40})
    assert r.status_code == 422


def test_blank_root_cause_exports_cleanly(api):
    down(api)
    csv = api.get("/api/history/export.csv", headers=api.h["operator"]).content.decode("utf-8-sig")
    assert "(not recorded)" in csv and "'-" not in csv
