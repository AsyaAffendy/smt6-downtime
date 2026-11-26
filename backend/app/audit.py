from . import db
from .util import actor, new_id, now


async def log(user, action, *, machine_id=None, event=None, details=None):
    """Append-only. The API exposes no way to edit or delete these entries."""
    await db.db.audit_logs.insert_one({
        "_id": new_id(), "at": now(), "action": action, "user": actor(user) if user else None,
        "machine_id": machine_id or (event or {}).get("machine_id"),
        "event_id": (event or {}).get("_id"), "event_no": (event or {}).get("event_no"),
        "details": details or {},
    })
