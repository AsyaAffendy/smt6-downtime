"""Downtime rules. Every change to a machine or event goes through this module.

Invariants
  1. At most one OPEN event per machine (lock here + unique index in MongoDB).
  2. While an event is OPEN it is the source of truth for the machine's status.
  3. Only confirm_recovery() closes an event. No status change ever does.
  4. Nothing is deleted. Edits keep before/after values in the audit log.
"""
import asyncio
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from . import audit, config, db
from .models import Status
from .security import PERMISSIONS
from .util import actor, new_id, now

_locks: dict = defaultdict(asyncio.Lock)
CLOCK_SKEW = timedelta(minutes=2)


def fail(message, code=409):
    raise HTTPException(code, message)


def resolve_time(value: datetime | None, label: str, not_before: datetime | None = None) -> datetime:
    current = now()
    if value is None:
        return current
    value = value.replace(microsecond=value.microsecond // 1000 * 1000)
    if value > current + CLOCK_SKEW:
        fail(f"{label} cannot be in the future", 422)
    value = min(value, current)
    if not_before and value < not_before:
        # Forms capture whole minutes, so accept the same minute and snap to the boundary.
        if value < not_before.replace(second=0, microsecond=0):
            local = not_before.astimezone(config.PLANT_TZ).strftime("%d %b %Y %H:%M")
            fail(f"{label} cannot be earlier than {local}", 422)
        value = not_before
    return value


async def get_machine(machine_id):
    machine = await db.db.machines.find_one({"_id": machine_id})
    if not machine:
        fail("Machine not found", 404)
    return machine


async def get_open_event(machine_id):
    return await db.db.downtime_events.find_one({"machine_id": machine_id, "state": "OPEN"})


async def get_event(event_id):
    event = await db.db.downtime_events.find_one({"_id": event_id})
    if not event:
        fail("Downtime event not found", 404)
    return event


def new_problem(data, user, at):
    return {"id": new_id(), **data.model_dump(), "status": "OPEN", "revision": 1, "actions": [], "parts": [],
            "created_at": at, "created_by": actor(user), "updated_at": at, "updated_by": actor(user),
            "resolved_at": None}


async def next_event_no(at):
    day = at.astimezone(config.PLANT_TZ).strftime("%Y%m%d")
    counter = await db.db.counters.find_one_and_update(
        {"_id": day}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return f"DT-{day}-{counter['seq']:03d}"


async def save_event(event, user):
    """Optimistic concurrency: the write only succeeds if nobody else changed the event."""
    version = event["version"]
    event.update(version=version + 1, updated_at=now(), updated_by=actor(user))
    result = await db.db.downtime_events.replace_one({"_id": event["_id"], "version": version}, event)
    if result.matched_count != 1:
        fail("This event was changed by someone else. Reload and try again.")


async def change_status(machine_id, body, user):
    async with _locks[machine_id]:
        machine = await get_machine(machine_id)
        event = await get_open_event(machine_id)
        at = now()
        if event:
            if body.status == Status.RUNNING:
                fail(f"{event['event_no']} is still open. Use 'Confirm production recovery' to set this machine RUNNING.")
            if body.status.value == event["machine_status"]:
                fail(f"Machine is already {body.status.value}")
            if body.problem or body.occurred_at:
                fail("A downtime event is already open. Add the new problem to that event.")
            previous = event["machine_status"]
            event["machine_status"] = body.status.value
            event["status_history"].append({"status": body.status.value, "from": previous, "at": at,
                                            "by": actor(user), "note": body.note})
            await save_event(event, user)
            await audit.log(user, "machine.status_changed", event=event,
                            details={"from": previous, "to": body.status.value, "note": body.note})
            return event

        if body.status == Status.DOWN:
            if not body.problem:
                fail("Describe the problem to open a downtime event", 422)
            last = await db.db.downtime_events.find({"machine_id": machine_id}).sort("recovered_at", -1).limit(1).to_list(1)
            not_before = last[0]["recovered_at"] if last else None
            # A backdated DOWN time must also not precede the last manually recorded status.
            if machine["status_since"] and (not not_before or machine["status_since"] > not_before):
                not_before = machine["status_since"]
            started = resolve_time(body.occurred_at, "DOWN time", not_before)
            event = {
                "_id": new_id(), "event_no": await next_event_no(started), "machine_id": machine_id,
                "open_key": machine_id, "state": "OPEN", "machine_status": Status.DOWN.value,
                "status_before": machine["status"], "started_at": started, "recorded_at": at,
                "recovered_at": None, "recovery": None,
                "problems": [new_problem(body.problem, user, at)], "attendance": [],
                "status_history": [{"status": "DOWN", "from": machine["status"], "at": started,
                                    "by": actor(user), "note": body.note}],
                "created_at": at, "created_by": actor(user), "updated_at": at, "updated_by": actor(user),
                "version": 1,
            }
            try:
                await db.db.downtime_events.insert_one(event)
            except DuplicateKeyError:
                fail("This machine already has an open downtime event")
            await audit.log(user, "event.opened", event=event,
                            details={"started_at": started, "backdated": body.occurred_at is not None,
                                     "problem": body.problem.description})
            return event

        if body.problem or body.occurred_at:
            fail("Problem and DOWN time apply only when setting a machine DOWN", 422)
        if body.status.value == machine["status"]:
            fail(f"Machine is already {body.status.value}")
        await db.db.machines.update_one({"_id": machine_id}, {"$set": {
            "status": body.status.value, "status_since": at, "updated_at": at, "updated_by": actor(user)}})
        await audit.log(user, "machine.status_changed", machine_id=machine_id,
                        details={"from": machine["status"], "to": body.status.value, "note": body.note})
        return None


async def mutate(event_id, user, apply, action, *, allow_closed=False):
    """Run one edit on an event under the machine lock. apply(event) returns audit details."""
    first = await get_event(event_id)
    async with _locks[first["machine_id"]]:
        event = await get_event(event_id)
        if event["state"] == "CLOSED":
            if not allow_closed:
                fail("This event is closed. If the machine has failed again, set it DOWN to open a new event.")
            if user["role"] not in {r.value for r in PERMISSIONS["event.amend_closed"]}:
                fail("Only a supervisor or admin can amend a closed event", 403)
        details = apply(event) or {}
        if event["state"] == "CLOSED":
            details["amended_after_close"] = True
        await save_event(event, user)
        await audit.log(user, action, event=event, details=details)
        return event


def find(items, item_id, label):
    for item in items:
        if item["id"] == item_id:
            return item
    fail(f"{label} not found", 404)


def touch(problem, user):
    problem.update(updated_at=now(), updated_by=actor(user))


async def add_problem(event_id, body, user):
    def apply(event):
        problem = new_problem(body, user, now())
        event["problems"].append(problem)
        return {"problem_id": problem["id"], **body.model_dump()}
    return await mutate(event_id, user, apply, "problem.added")


async def update_problem(event_id, problem_id, body, user):
    def apply(event):
        problem = find(event["problems"], problem_id, "Problem")
        if body.expected_revision != problem["revision"]:
            fail("This problem was updated by someone else. Reload and try again.")
        before, after = {}, {}
        for key, value in body.model_dump(exclude_none=True, exclude={"expected_revision"}).items():
            if problem[key] != value:
                before[key], after[key] = problem[key], value
        if not after:
            fail("No changes to save", 422)
        problem.update(after)
        problem["revision"] += 1
        if "status" in after:
            problem["resolved_at"] = now() if after["status"] == "RESOLVED" else None
        touch(problem, user)
        return {"problem_id": problem_id, "before": before, "after": after}
    return await mutate(event_id, user, apply, "problem.updated", allow_closed=True)


async def add_to_problem(event_id, problem_id, field, body, user, action):
    def apply(event):
        problem = find(event["problems"], problem_id, "Problem")
        entry = {"id": new_id(), **body.model_dump(), "at": now(), "by": actor(user)}
        problem[field].append(entry)
        touch(problem, user)
        return {"problem_id": problem_id, **body.model_dump()}
    return await mutate(event_id, user, apply, action, allow_closed=True)


async def check_in(event_id, body, user):
    def apply(event):
        name = body.technician_name or user["full_name"]
        if any(a["technician_name"].casefold() == name.casefold() and not a["left_at"] for a in event["attendance"]):
            fail(f"{name} is already checked in on this event")
        arrived = resolve_time(body.arrived_at, "Arrival time", event["started_at"])
        previous = [a["left_at"] for a in event["attendance"]
                    if a["technician_name"].casefold() == name.casefold() and a["left_at"]]
        if previous and arrived < max(previous):
            arrived = resolve_time(body.arrived_at, "Arrival time", max(previous))
        entry = {"id": new_id(), "technician_name": name, "arrived_at": arrived, "left_at": None,
                 "note": body.note, "recorded_at": now(), "recorded_by": actor(user),
                 "checkout_by": None, "auto_checkout": False}
        event["attendance"].append(entry)
        return {"technician": name, "arrived_at": arrived}
    return await mutate(event_id, user, apply, "attendance.check_in")


async def check_out(event_id, attendance_id, body, user):
    def apply(event):
        entry = find(event["attendance"], attendance_id, "Attendance record")
        if entry["left_at"]:
            fail("Already checked out")
        entry["left_at"] = resolve_time(body.left_at, "Departure time", entry["arrived_at"])
        entry["checkout_by"] = actor(user)
        return {"technician": entry["technician_name"], "left_at": entry["left_at"]}
    return await mutate(event_id, user, apply, "attendance.check_out")


async def confirm_recovery(event_id, body, user):
    if not body.production_confirmed:
        fail("Confirm that actual production has resumed before closing the event", 422)
    first = await get_event(event_id)
    async with _locks[first["machine_id"]]:
        event = await get_event(event_id)
        if event["state"] != "OPEN":
            fail("This event is already closed")
        latest = [event["started_at"], event["status_history"][-1]["at"]]
        latest += [t for a in event["attendance"] for t in (a["arrived_at"], a["left_at"]) if t]
        recovered = resolve_time(body.recovered_at, "Recovery time", max(latest))
        at = now()
        closed = deepcopy(event)
        for a in closed["attendance"]:
            if not a["left_at"]:
                a.update(left_at=recovered, auto_checkout=True, checkout_by=actor(user))
        closed["status_history"].append({"status": "RUNNING", "from": closed["machine_status"], "at": recovered,
                                         "by": actor(user), "note": body.verification_note})
        closed.update(state="CLOSED", machine_status="RUNNING", recovered_at=recovered,
                      recovery={"confirmed_by": actor(user), "confirmed_at": at, "note": body.verification_note,
                                "unresolved_problems": sum(p["status"] == "OPEN" for p in closed["problems"])})
        del closed["open_key"]
        # Machine first: until the event write succeeds, the open event still overrides it.
        previous = await get_machine(closed["machine_id"])
        await db.db.machines.update_one({"_id": closed["machine_id"]}, {"$set": {
            "status": "RUNNING", "status_since": recovered, "updated_at": at, "updated_by": actor(user)}})
        try:
            await save_event(closed, user)
        except Exception:
            await db.db.machines.replace_one({"_id": previous["_id"]}, previous)
            raise
        await audit.log(user, "event.closed", event=closed, details={
            "recovered_at": recovered, "verification_note": body.verification_note})
        return closed
