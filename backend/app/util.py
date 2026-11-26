import uuid
from datetime import datetime, timezone


def now() -> datetime:
    # MongoDB stores millisecond precision; match it so timestamps round-trip exactly.
    t = datetime.now(timezone.utc)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


def new_id() -> str:
    return uuid.uuid4().hex


def actor(user: dict) -> dict:
    return {"id": user["_id"], "username": user["username"], "name": user["full_name"], "role": user["role"]}


def out(doc):
    """Make a Mongo document JSON-friendly."""
    if isinstance(doc, dict):
        return {("id" if k == "_id" else k): out(v) for k, v in doc.items() if k not in ("password_hash", "open_key", "token_version")}
    if isinstance(doc, list):
        return [out(v) for v in doc]
    if isinstance(doc, datetime):
        return doc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return doc


def duration_seconds(event: dict, at: datetime | None = None) -> int:
    end = event.get("recovered_at") or at or now()
    return max(0, int((end - event["started_at"]).total_seconds()))
