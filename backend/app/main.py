import asyncio
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pymongo.errors import DuplicateKeyError

from . import audit, config, db, live, reports, seed, workflow
from .models import (CATEGORIES, ActionIn, AttendanceIn, CheckoutIn, LoginIn, PartIn, PasswordChange, ProblemIn,
                     ProblemUpdate, RecoveryIn, Status, StatusChange, UserIn, UserUpdate)
from .security import (check_rate, clear_failures, current_user, hash_password, make_token, permissions_for,
                       record_failure, require, verify_password)
from .util import actor, duration_seconds, now, out


@asynccontextmanager
async def lifespan(_):
    config.validate()
    await db.connect()
    await seed.run()
    yield
    await db.close()


docs = config.APP_ENV != "production"
app = FastAPI(title="SMT6 Downtime Monitoring API", lifespan=lifespan,
              docs_url="/api/docs" if docs else None, redoc_url=None,
              openapi_url="/api/openapi.json" if docs else None)
if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def event_out(e):
    return out({**e, "duration_seconds": duration_seconds(e)})


# ---------- public (view-only) ----------
@app.get("/api/health")
async def health():
    await db.db.machines.count_documents({})
    return {"ok": True}


@app.get("/api/public/dashboard")
async def dashboard():
    return await live.snapshot()


@app.websocket("/ws/dashboard")
async def dashboard_socket(ws: WebSocket):
    await ws.accept()
    try:
        await live.send_initial(ws)
        while True:
            # Incoming messages are ignored (view-only). Heartbeat lets screens detect a dead link.
            try:
                await asyncio.wait_for(ws.receive_text(), 15)
            except asyncio.TimeoutError:
                await live.heartbeat(ws)
                if ws not in live.clients:
                    break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        live.clients.discard(ws)


# ---------- authentication ----------
def profile(user):
    return {**actor(user), "permissions": permissions_for(user["role"])}


@app.post("/api/auth/login")
async def login(body: LoginIn, request: Request):
    username = body.username.lower()
    key = (username, request.client.host if request.client else "")
    check_rate(key)
    user = await db.db.users.find_one({"username": username})
    if not user or not user["active"] or not verify_password(body.password, user["password_hash"]):
        record_failure(key)
        await audit.log(None, "auth.login_failed", details={"username": username})
        raise HTTPException(401, "Incorrect username or password")
    clear_failures(key)
    await audit.log(user, "auth.login")
    return {"token": make_token(user), "user": profile(user)}


@app.get("/api/auth/me")
async def me(user=Depends(current_user)):
    return profile(user)


@app.post("/api/auth/password")
async def change_password(body: PasswordChange, user=Depends(current_user)):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(422, "Current password is incorrect")
    user = {**user, "password_hash": hash_password(body.new_password), "token_version": user["token_version"] + 1,
            "updated_at": now(), "updated_by": actor(user)}
    await db.db.users.replace_one({"_id": user["_id"]}, user)
    await audit.log(user, "auth.password_changed")
    return {"token": make_token(user), "user": profile(user)}


# ---------- control ----------
@app.get("/api/meta")
async def meta(user=Depends(current_user)):
    return {"categories": CATEGORIES, "statuses": [s.value for s in Status], "machines": config.MACHINE_IDS}


@app.get("/api/control/machines/{machine_id}")
async def machine_detail(machine_id: str, user=Depends(require("machine.status"))):
    machine = await workflow.get_machine(machine_id)
    event = await workflow.get_open_event(machine_id)
    if event:
        machine.update(status=event["machine_status"], status_since=event["status_history"][-1]["at"])
    return {"machine": out(machine), "open_event": event_out(event) if event else None}


async def done(coro):
    result = await coro
    await live.broadcast()
    return event_out(result) if result else None


@app.post("/api/control/machines/{machine_id}/status")
async def set_status(machine_id: str, body: StatusChange, user=Depends(require("machine.status"))):
    return {"event": await done(workflow.change_status(machine_id, body, user))}


@app.post("/api/events/{event_id}/problems")
async def add_problem(event_id: str, body: ProblemIn, user=Depends(require("event.work"))):
    return await done(workflow.add_problem(event_id, body, user))


@app.patch("/api/events/{event_id}/problems/{problem_id}")
async def edit_problem(event_id: str, problem_id: str, body: ProblemUpdate, user=Depends(require("event.work"))):
    return await done(workflow.update_problem(event_id, problem_id, body, user))


@app.post("/api/events/{event_id}/problems/{problem_id}/actions")
async def add_action(event_id: str, problem_id: str, body: ActionIn, user=Depends(require("event.work"))):
    return await done(workflow.add_to_problem(event_id, problem_id, "actions", body, user, "action.added"))


@app.post("/api/events/{event_id}/problems/{problem_id}/parts")
async def add_part(event_id: str, problem_id: str, body: PartIn, user=Depends(require("event.work"))):
    return await done(workflow.add_to_problem(event_id, problem_id, "parts", body, user, "part.added"))


@app.post("/api/events/{event_id}/attendance")
async def check_in(event_id: str, body: AttendanceIn, user=Depends(require("event.work"))):
    return await done(workflow.check_in(event_id, body, user))


@app.post("/api/events/{event_id}/attendance/{attendance_id}/checkout")
async def check_out(event_id: str, attendance_id: str, body: CheckoutIn, user=Depends(require("event.work"))):
    return await done(workflow.check_out(event_id, attendance_id, body, user))


@app.post("/api/events/{event_id}/recovery")
async def recover(event_id: str, body: RecoveryIn, user=Depends(require("event.recover"))):
    return await done(workflow.confirm_recovery(event_id, body, user))


# ---------- history, reports, audit ----------
def filters(machine: Optional[str] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
            q: Optional[str] = Query(None, max_length=200), state: Optional[Literal["OPEN", "CLOSED"]] = None,
            category: Optional[str] = None):
    return dict(machine=machine, date_from=date_from, date_to=date_to, q=q, state=state, category=category)


@app.get("/api/history/events")
async def history(f=Depends(filters), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                  user=Depends(require("history.view"))):
    events = await reports.search(**f)
    chunk = events[(page - 1) * page_size: page * page_size]
    return {"total": len(events), "page": page, "page_size": page_size,
            "items": [event_out(e) for e in chunk], "summary": reports.summarise(events)}


@app.get("/api/history/events/{event_id}")
async def event_detail(event_id: str, user=Depends(require("history.view"))):
    return event_out(await workflow.get_event(event_id))


@app.get("/api/history/export.{fmt}")
async def export(fmt: Literal["csv", "xlsx"], f=Depends(filters), user=Depends(require("history.view"))):
    events = await reports.search(**f)
    data = reports.to_csv(events) if fmt == "csv" else reports.to_xlsx(events)
    await audit.log(user, "report.exported", details={"format": fmt, "events": len(events),
                    "filters": {k: str(v) for k, v in f.items() if v}})
    media = "text/csv" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="smt6-downtime.{fmt}"'})


@app.get("/api/audit")
async def audit_log(machine: Optional[str] = None, event_no: Optional[str] = None,
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                    user=Depends(require("audit.view"))):
    query = {}
    if machine:
        query["machine_id"] = machine
    if event_no:
        query["event_no"] = event_no.strip().upper()
    total = await db.db.audit_logs.count_documents(query)
    items = await db.db.audit_logs.find(query).sort("at", -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": out(items)}


# ---------- user management (accounts are deactivated, never deleted) ----------
@app.get("/api/users")
async def list_users(user=Depends(require("users.manage"))):
    return out(await db.db.users.find({}).sort("username", 1).to_list(None))


@app.post("/api/users", status_code=201)
async def add_user(body: UserIn, user=Depends(require("users.manage"))):
    try:
        created = await seed.create_user(body.username, body.full_name, body.role.value, body.password, actor(user))
    except DuplicateKeyError:
        raise HTTPException(409, "That username already exists")
    await audit.log(user, "user.created", details={"username": body.username, "role": body.role.value})
    return out(created)


@app.patch("/api/users/{user_id}")
async def edit_user(user_id: str, body: UserUpdate, user=Depends(require("users.manage"))):
    target = await db.db.users.find_one({"_id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_none=True, mode="json")
    if user_id == user["_id"] and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(409, "You cannot deactivate or demote your own account")
    logged = {k: v for k, v in changes.items() if k != "password"}
    if "password" in changes:
        target["password_hash"] = hash_password(changes.pop("password"))
        target["token_version"] += 1
        logged["password_reset"] = True
    target.update(changes, updated_at=now(), updated_by=actor(user))
    await db.db.users.replace_one({"_id": user_id}, target)
    await audit.log(user, "user.updated", details={"username": target["username"], **logged})
    return out(target)
