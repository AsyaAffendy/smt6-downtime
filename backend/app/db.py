"""MongoDB access. MONGO_URL=memory:// gives a throwaway in-memory database for demos/tests."""
from datetime import timezone

from bson.codec_options import CodecOptions

from . import config

client = None
db = None


async def connect():
    global client, db
    if config.MONGO_URL.startswith("memory://"):
        if config.APP_ENV == "production":
            raise RuntimeError("The in-memory database cannot be used in production")
        from mongomock_motor import AsyncMongoMockClient  # dev dependency only
        client = AsyncMongoMockClient(tz_aware=True)
        db = client[config.MONGO_DB]
    else:
        from pymongo import AsyncMongoClient
        client = AsyncMongoClient(config.MONGO_URL, serverSelectionTimeoutMS=5000)
        db = client.get_database(config.MONGO_DB, codec_options=CodecOptions(tz_aware=True, tzinfo=timezone.utc))
        await client.admin.command("ping")
    await ensure_indexes()


async def ensure_indexes():
    await db.users.create_index("username", unique=True)
    # open_key exists only while an event is open: the database itself rejects a second open event.
    await db.downtime_events.create_index("open_key", unique=True, sparse=True)
    await db.downtime_events.create_index("event_no", unique=True)
    await db.downtime_events.create_index([("machine_id", 1), ("started_at", -1)])
    await db.downtime_events.create_index([("started_at", -1)])
    await db.audit_logs.create_index([("at", -1)])
    await db.audit_logs.create_index([("machine_id", 1), ("at", -1)])


async def close():
    if client is not None and not config.MONGO_URL.startswith("memory://"):
        await client.close()
