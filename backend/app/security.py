import time
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db
from .models import Role
from .util import now

bearer = HTTPBearer(auto_error=False)

# Single place to adjust who may do what.
ALL = {Role.OPERATOR, Role.TECHNICIAN, Role.SUPERVISOR, Role.ADMIN}
TECH = {Role.TECHNICIAN, Role.SUPERVISOR, Role.ADMIN}
LEAD = {Role.SUPERVISOR, Role.ADMIN}
PERMISSIONS = {
    "machine.status": ALL,      # includes reporting DOWN, which opens an event
    "event.recover": ALL,       # confirm production recovery
    "event.work": TECH,         # problems, actions, parts, attendance
    "event.amend_closed": LEAD,
    "history.view": ALL,
    "audit.view": LEAD,
    "users.manage": {Role.ADMIN},
}


def permissions_for(role: str):
    return sorted(p for p, roles in PERMISSIONS.items() if Role(role) in roles)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: dict) -> str:
    return jwt.encode({"sub": user["_id"], "tv": user.get("token_version", 0),
                       "exp": now() + timedelta(hours=config.TOKEN_HOURS)}, config.JWT_SECRET, algorithm="HS256")


async def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if cred is None:
        raise HTTPException(401, "Sign in required")
    try:
        claims = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please sign in again.")
    user = await db.db.users.find_one({"_id": claims["sub"]})
    # Checked on every request so deactivation / password reset takes effect immediately.
    if not user or not user["active"] or user.get("token_version", 0) != claims.get("tv"):
        raise HTTPException(401, "Session is no longer valid")
    return user


def require(permission: str):
    async def dep(user=Depends(current_user)):
        if Role(user["role"]) not in PERMISSIONS[permission]:
            raise HTTPException(403, "Your role does not allow this action")
        return user
    return dep


# Simple per-process brute-force limiter.
_failures: dict = {}
WINDOW, LIMIT = 300, 8


def check_rate(key):
    recent = [t for t in _failures.get(key, []) if time.monotonic() - t < WINDOW]
    _failures[key] = recent
    if len(recent) >= LIMIT:
        raise HTTPException(429, "Too many failed sign-ins. Wait a few minutes.")


def record_failure(key):
    _failures.setdefault(key, []).append(time.monotonic())


def clear_failures(key):
    _failures.pop(key, None)
