"""Creates the four machines and first admin. Sample data is added only when SEED_DEMO=true."""
from datetime import timedelta

from . import config, db
from .security import hash_password
from .util import actor, new_id, now

DEMO_USERS = [("admin", "System Admin", "admin"), ("supervisor", "Sample Supervisor", "supervisor"),
              ("tech1", "Sample Tech A", "technician"), ("tech2", "Sample Tech B", "technician"),
              ("operator", "Sample Operator", "operator")]
DEMO_PASSWORD = "Demo-Pass-123"


async def create_user(username, full_name, role, password, by=None):
    user = {"_id": new_id(), "username": username, "full_name": full_name, "role": role, "active": True,
            "password_hash": hash_password(password), "token_version": 0, "created_at": now(), "created_by": by,
            "updated_at": now(), "updated_by": by}
    await db.db.users.insert_one(user)
    return user


async def run():
    fresh = await db.db.machines.count_documents({}) == 0
    for machine_id in config.MACHINE_IDS:
        await db.db.machines.update_one({"_id": machine_id}, {"$setOnInsert": {
            "status": "IDLE", "status_since": None, "updated_at": now(), "updated_by": None}}, upsert=True)
    if await db.db.users.count_documents({}) == 0:
        if config.SEED_DEMO:
            for username, name, role in DEMO_USERS:
                await create_user(username, name, role, DEMO_PASSWORD)
        elif 10 <= len(config.ADMIN_PASSWORD.encode()) <= 72:
            await create_user("admin", "System Admin", "admin", config.ADMIN_PASSWORD)
        else:
            raise RuntimeError("First start: set ADMIN_PASSWORD (10-72 characters) or SEED_DEMO=true")
    if config.SEED_DEMO and fresh:
        await sample_data()


async def sample_data():
    users = {u["username"]: actor(u) for u in await db.db.users.find({}).to_list(None)}
    t = now()

    def problem(desc, cat, cause, status, at, actions=(), parts=()):
        by = users["tech1"]
        return {"id": new_id(), "description": desc, "category": cat, "root_cause": cause, "status": status, "revision": 1,
                "actions": [{"id": new_id(), "type": k, "description": d, "at": at + timedelta(minutes=8), "by": by}
                            for k, d in actions],
                "parts": [{"id": new_id(), "part_name": n, "part_number": pn, "quantity": 1, "source": s,
                           "donor_machine": dm, "donor_details": dd, "at": at + timedelta(minutes=12), "by": by}
                          for n, pn, s, dm, dd in parts],
                "created_at": at, "created_by": by, "updated_at": at, "updated_by": by,
                "resolved_at": at + timedelta(minutes=20) if status == "RESOLVED" else None}

    async def event(machine, ago_min, length_min, problems, techs, status="DOWN"):
        start = t - timedelta(minutes=ago_min)
        end = start + timedelta(minutes=length_min) if length_min else None
        op = users["operator"]
        history = [{"status": "DOWN", "from": "RUNNING", "at": start, "by": op, "note": "Sample data"}]
        if status != "DOWN" and not end:
            history.append({"status": status, "from": "DOWN", "at": t - timedelta(minutes=6),
                            "by": users["tech2"], "note": "Sample data"})
        if end:
            history.append({"status": "RUNNING", "from": "DOWN", "at": end, "by": op, "note": "Sample data"})
        day = start.astimezone(config.PLANT_TZ).strftime("%Y%m%d")
        counter = await db.db.counters.find_one_and_update(
            {"_id": day}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
        doc = {
            "_id": new_id(), "event_no": f"DT-{day}-{counter['seq']:03d}", "machine_id": machine,
            "state": "CLOSED" if end else "OPEN", "machine_status": "RUNNING" if end else status,
            "status_before": "RUNNING", "started_at": start, "recorded_at": start, "recovered_at": end,
            "recovery": {"confirmed_by": op, "confirmed_at": end, "note": "Sample: production verified",
                         "unresolved_problems": 0} if end else None,
            "problems": [problem(*p[:4], start + timedelta(minutes=i * 7), *p[4:]) for i, p in enumerate(problems)],
            "attendance": [{"id": new_id(), "technician_name": users[u]["name"],
                            "arrived_at": start + timedelta(minutes=5 + i * 6), "left_at": end, "note": "",
                            "recorded_at": start + timedelta(minutes=5 + i * 6), "recorded_by": users[u],
                            "checkout_by": op if end else None, "auto_checkout": bool(end)}
                           for i, u in enumerate(techs)],
            "status_history": history, "created_at": start, "created_by": op,
            "updated_at": end or t, "updated_by": op, "version": 1, "is_sample": True,
        }
        if not end:
            doc["open_key"] = machine
        await db.db.downtime_events.insert_one(doc)
        await db.db.audit_logs.insert_one({
            "_id": new_id(), "at": t, "action": "sample.event_seeded", "user": None, "machine_id": machine,
            "event_id": doc["_id"], "event_no": doc["event_no"], "details": {"sample_data": True}})

    feeder = ("Feeder pickup errors on front bank", "Feeder", "Worn feeder sprocket", "RESOLVED",
              [("TROUBLESHOOTING", "Swapped feeder to another slot; fault followed the feeder"),
               ("CORRECTIVE", "Replaced feeder and verified pickup offset")],
              [("8mm tape feeder", "SAMPLE-FDR-08", "STORE", "", "")])
    vision = ("Component recognition failure at vision station", "Vision / Camera", "Contaminated camera cover glass",
              "RESOLVED", [("CORRECTIVE", "Cleaned cover glass and re-ran vision check")])
    conveyor = ("Board stuck at exit conveyor", "Conveyor / Transport", "Damaged conveyor belt", "RESOLVED",
                [("CORRECTIVE", "Replaced belt")], [("Conveyor belt", "SAMPLE-BLT-01", "STORE", "", "")])
    await event("SMT6-0014", 60 * 74, 48, [feeder], ["tech1"])
    await event("SMT6-0015", 60 * 50, 95, [vision, conveyor], ["tech2"])
    await event("SMT6-0044", 60 * 27, 34, [conveyor], ["tech1"])
    await event("SMT6-0014", 60 * 22, 26, [vision], ["tech2"])
    await event("SMT6-0015", 47, None, [
        ("Vacuum error on placement head", "Pneumatic / Vacuum", "", "OPEN",
         [("TROUBLESHOOTING", "Checked vacuum filter and tubing for leaks")],
         [("Vacuum ejector", "SAMPLE-VAC-02", "DONOR_MACHINE", "SMT6-0052", "Sample: borrowed from spare head")]),
        ("Nozzle changer alignment alarm", "Nozzle / Head", "", "OPEN")], ["tech1"])
    await event("SMT6-0044", 83, None, [
        ("Y-axis servo overload alarm", "Motion / Servo", "Cable chain obstruction", "OPEN",
         [("CORRECTIVE", "Rerouted obstructing cable; running test boards")])], ["tech2"], "TESTING/RECOVERY")
    for machine, status, minutes in [("SMT6-0014", "RUNNING", 60 * 21), ("SMT6-0015", "RUNNING", 60 * 48),
                                     ("SMT6-0044", "RUNNING", 60 * 26), ("SMT6-0052", "SETUP", 18)]:
        await db.db.machines.update_one({"_id": machine}, {"$set": {
            "status": status, "status_since": t - timedelta(minutes=minutes)}})
