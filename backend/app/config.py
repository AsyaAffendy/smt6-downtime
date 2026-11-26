import os
from zoneinfo import ZoneInfo

APP_ENV = os.getenv("APP_ENV", "development")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "smt6_downtime")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-before-production")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
PLANT_TZ_NAME = os.getenv("PLANT_TIMEZONE", "Asia/Kuala_Lumpur")
PLANT_TZ = ZoneInfo(PLANT_TZ_NAME)
SEED_DEMO = os.getenv("SEED_DEMO", "false").lower() == "true"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]

MACHINE_IDS = ["SMT6-0014", "SMT6-0015", "SMT6-0044", "SMT6-0052"]


def validate():
    if APP_ENV == "production":
        if JWT_SECRET.startswith(("dev-only", "change-me")) or len(JWT_SECRET) < 32:
            raise RuntimeError("Set JWT_SECRET to a random value of at least 32 characters")
        if SEED_DEMO:
            raise RuntimeError("SEED_DEMO must be false in production")
