"""WebSocket fan-out. In-process, so run a single API worker (see README)."""
import asyncio
import logging

from fastapi import WebSocket

from . import config, db
from .util import duration_seconds, now, out

clients: set[WebSocket] = set()
_send_lock = asyncio.Lock()


async def snapshot() -> dict:
    """Public, view-only data. Only fields listed here ever reach the dashboard."""
    machines = await db.db.machines.find({}).sort("_id", 1).to_list(None)
    open_events = {e["machine_id"]: e for e in await db.db.downtime_events.find({"state": "OPEN"}).to_list(None)}
    cards = []
    for m in machines:
        ev = open_events.get(m["_id"])
        card = {"id": m["_id"], "status": m["status"], "status_since": m["status_since"], "event": None}
        if ev:
            card["status"] = ev["machine_status"]
            card["status_since"] = ev["status_history"][-1]["at"]
            unresolved = [p for p in ev["problems"] if p["status"] == "OPEN"]
            card["event"] = {
                "event_no": ev["event_no"], "started_at": ev["started_at"],
                "problem_count": len(ev["problems"]),
                "problems": [{"description": p["description"], "category": p["category"], "status": p["status"]}
                             for p in (unresolved or ev["problems"][-1:])],
                "technicians": [a["technician_name"] for a in ev["attendance"] if not a["left_at"]],
                "duration_seconds": duration_seconds(ev),
            }
        cards.append(card)
    return out({"type": "snapshot", "server_time": now(), "timezone": config.PLANT_TZ_NAME, "machines": cards})


async def _send(ws, message):
    try:
        await asyncio.wait_for(ws.send_json(message), 3)
    except Exception:
        clients.discard(ws)


async def broadcast():
    """Called after a change is saved, so it must never raise. The heartbeat catches up if it fails."""
    try:
        # The lock keeps snapshots in order, so an older one can never overwrite a newer one.
        async with _send_lock:
            if clients:
                message = await snapshot()
                await asyncio.gather(*(_send(ws, message) for ws in list(clients)))
    except Exception:
        logging.getLogger(__name__).exception("Live update failed")


async def send_initial(ws):
    async with _send_lock:
        await ws.send_json(await snapshot())
        clients.add(ws)


async def heartbeat(ws):
    async with _send_lock:
        await _send(ws, await snapshot())
