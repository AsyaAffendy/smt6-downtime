# SMT6 Machine Downtime Monitoring System

Standalone system for SMT6-0014, SMT6-0015, SMT6-0044 and SMT6-0052. Status is entered manually;
there is no machine connectivity.

React + Tailwind · FastAPI · MongoDB · WebSockets

> **Verification status:** automated tests and screen checks were run against an **in-memory MongoDB
> substitute**. A real MongoDB server and the Docker build have **not** been run yet. Do the
> "Before factory use" checks below.

## Try it locally (sample data, no MongoDB needed)

Tested with Python 3.13 and Node 22. Needs Python 3.11+ and Node 20.19+ or 22.12+. Run from the project folder.

Terminal 1 (backend):

    cd backend
    python -m venv .venv
    source .venv/bin/activate          # Windows: .venv\Scripts\activate
    pip install -r requirements-dev.txt
    MONGO_URL=memory:// SEED_DEMO=true uvicorn app.main:app --port 8000

On Windows PowerShell, replace the last line with:

    $env:MONGO_URL="memory://"; $env:SEED_DEMO="true"; uvicorn app.main:app --port 8000

Terminal 2 (frontend):

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. **`memory://` loses all data when the backend stops.** To keep data,
set `MONGO_URL` to a real server (default `mongodb://localhost:27017`).

Demo accounts (created only with `SEED_DEMO=true`), all with password `Demo-Pass-123`:
`admin`, `supervisor`, `tech1`, `tech2`, `operator`.

Sample events, names and part numbers are made up.

## Pages

| Page | Path | Access |
|---|---|---|
| Public dashboard (view-only) | `/` | Anyone who can reach the site |
| Input / Control | `/control` | Signed in |
| History & Reports (CSV, Excel) | `/history` | Signed in |
| Audit Log | `/audit` | Supervisor, Admin |
| Users | `/users` | Admin |

## Roles

These are proposed defaults. Change them in `backend/app/security.py` (`PERMISSIONS`).

| Action | Operator | Technician | Supervisor | Admin |
|---|:-:|:-:|:-:|:-:|
| Change status, including DOWN (opens an event) | ✓ | ✓ | ✓ | ✓ |
| Confirm production recovery | ✓ | ✓ | ✓ | ✓ |
| Problems, actions, parts, attendance on open events | | ✓ | ✓ | ✓ |
| Amend problems / actions / parts on closed events | | | ✓ | ✓ |
| View history and export | ✓ | ✓ | ✓ | ✓ |
| View audit log | | | ✓ | ✓ |
| Manage users | | | | ✓ |

## Downtime rules

- Setting a machine **DOWN** opens an event and starts the timer. A first problem is required.
- While it is open, the machine can move between DOWN, TESTING/RECOVERY, SETUP and IDLE. It stays the
  **same event and the timer keeps running**, including IDLE and SETUP time.
- More problems are added to the open event. A second open event per machine is rejected.
- **Only "Confirm production recovery"** closes an event. It needs a tick box and a verification note,
  and sets the machine RUNNING. Technicians still checked in are checked out at the recovery time.
- Problems still marked OPEN do not block closing. The screen warns, and the count is stored.
- A later breakdown creates a new event. Closed events cannot be reopened.
- DOWN, arrival, departure and recovery times can be backdated for late entry. They cannot be in the
  future or out of order. The system also stores when each event, attendance and closure was entered
  (for departures, see the audit log).

## Data model

| Collection | Contents |
|---|---|
| `users` | Accounts, roles, password hashes, who created/updated each |
| `machines` | The four machines and their status **when no event is open** |
| `downtime_events` | One document per breakdown: `problems[]` (with `actions[]`, `parts[]`), `attendance[]`, `status_history[]`, `recovery` |
| `audit_logs` | Who did what and when, with before/after values for problem edits |
| `counters` | Daily sequence for event numbers (`DT-YYYYMMDD-001`) |

While an event is open, **its `machine_status` is the machine's current status**; `machines.status`
is not updated until recovery. Anything reading MongoDB directly must check for an open event first,
or use `/api/public/dashboard`.

## Records and audit

- The API has no delete operation for any record. Users are deactivated instead.
- Actions and parts are append-only. Correct a mistake by adding another entry.
- Problem edits store before and after values in the audit log.
- Each record stores who created and updated it.
- **Limit:** event times and attendance entries cannot be edited after saving.
- **Limit:** anyone with direct database access can still change data. Restrict that access and back up.
- **Limit:** MongoDB transactions are not used. Each event keeps its own status timeline in the same
  write, but a crash between a change and its audit entry could leave that audit entry missing.

## Reports

Date filters use the DOWN time in the plant time zone. Open events count up to now. An event is
counted once, in the period it started. Technician time on overlapping events is added for each.
CSV has one row per event. Excel has Events, Problems, Actions, Parts and Attendance sheets.

## Tests

    cd backend
    pytest

Against a real MongoDB (**drops the database `smt6_test`**):

    TEST_MONGO_URL=mongodb://localhost:27017 pytest

## Deployment (Docker)

    cp .env.example .env      # fill in the blank values
    docker compose up -d --build

The site is on port 8080. Sign in as `admin` with `ADMIN_PASSWORD`, change the password, create
named accounts, then clear `ADMIN_PASSWORD` from `.env`.

For a Docker demo, set `APP_ENV=development` and `SEED_DEMO=true`. Use a separate Compose project
(`docker compose -p smt6demo up`) so sample data never reaches the production database.

### Before factory use

1. Run the tests against your real MongoDB version.
2. Run the Docker build, then check sign-in and live updates from a second device.
3. **Add HTTPS** (company reverse proxy or certificate in nginx). The supplied setup is plain HTTP,
   which sends passwords unencrypted.
4. Keep the site on the factory network. The public dashboard shows problems and technician names
   to anyone who can reach it.
5. Schedule backups with `mongodump` and test a restore.
6. Keep one backend worker. Running several needs shared locking and messaging for live updates.
7. Keep the server clock synchronised (NTP), and set screens and tablets to the plant time zone,
   since typed times use the device's time zone.

History search and report totals load all matching events into memory. This suits a four-machine
site; revisit it if the history grows very large.
