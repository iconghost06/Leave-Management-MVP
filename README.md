# Leave Management MVP

## 1. What this is

A leave management web app for a small organisation. Employees sign up, see their Earned and Sick balances, request leave and cancel requests that are still pending. Managers approve or reject other people's requests, and every balance stays correct and never goes negative, even when two people act at the same moment.

The backend is a FastAPI service on PostgreSQL, and the frontend is a React single-page app built with Vite. The rules that matter most (no overlapping leave, no over-spending a balance, no approving your own request) are enforced in the service layer and again by database constraints.

## 2. Live demo

- Frontend: https://leave-management-mvp-1.onrender.com
- API docs (Swagger UI): https://leave-management-mvp.onrender.com/docs

The backend runs on a free Render web service that sleeps when idle. **The first request after a quiet period can take about a minute** while it wakes up. The login page shows "The server may be waking up, please wait." after 5 seconds. The database (Neon free plan) also suspends when idle, so that first request can be a little slower still.

Demo accounts (created by the seed script on every backend start; they are for demonstration only):

| User | Role | Email | Password | Reports to |
|---|---|---|---|---|
| `supermanager` | Super manager | `supermanager@example.com` | `Manager@123` | nobody |
| `manager1` | Manager | `manager1@example.com` | `Manager@123` | `supermanager` |
| `manager2` | Manager | `manager2@example.com` | `Manager@123` | `supermanager` |
| `employee1` | Employee | `employee1@example.com` | `Employee@123` | `manager1` |
| `employee2` | Employee | `employee2@example.com` | `Employee@123` | `manager2` |
| `employee3` | Employee | `employee3@example.com` | `Employee@123` | `manager1` |
| `employee4` | Employee | `employee4@example.com` | `Employee@123` | `manager2` |

Employee requests can be decided by any manager. A manager's own request can be decided only by the manager they report to, which for `manager1` and `manager2` is the super manager.

The "Reports to" column is the assigned manager. It is **informational**: the screens show it (the employee sees "Sent to", managers see "Assigned manager"), but it does not change who may approve or reject. For example, `manager2` can decide `employee1`'s request even though `employee1` is assigned to `manager1`. Team-only visibility, where a manager sees and decides only their own team, is a possible improvement (see section 11).

To try signup you need the company join code. It is provided in the submission email and is not written in this repository. Signup always creates an employee. Managers exist only through the seed script.

## 3. Tech stack

| Part | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), psycopg 3, Alembic, pydantic-settings |
| Auth | Argon2 password hashes (`pwdlib`), JWT bearer tokens (`PyJWT`, HS256, 60-minute expiry) |
| Database | PostgreSQL 16 with the `btree_gist` extension |
| Frontend | React 18, react-router-dom 6, Vite 6, plain JavaScript, one stylesheet, no UI or state library |
| Backend tests | pytest and httpx, run against a real PostgreSQL database |
| Hosting | Render (web service and static site), Neon (PostgreSQL) |

## 4. Architecture

The browser downloads the React app from a static site. Once loaded, the app calls the FastAPI service directly over HTTPS with `fetch`, sending the JWT in an `Authorization: Bearer` header. FastAPI is the only thing that talks to PostgreSQL. Every business rule is enforced on the server; the route guards and buttons in the UI only shape what a user sees.

```
Browser
  │
  ├─ downloads HTML/JS/CSS ───────────▶  React static site (Render)
  │
  └─ fetch + Authorization: Bearer ───▶  FastAPI (Render web service)
                                              │  SQLAlchemy
                                              ▼
                                         PostgreSQL (Neon)
```

Backend layering (`backend/app/`):

- `routers/` handle HTTP only: they parse input with Pydantic schemas, resolve dependencies (`get_db`, `get_current_user`, `require_manager`) and call one service function.
- `services/` hold the rules, take the locks and call `commit()` exactly once, as their last step. A rule failure is raised as `AppError(status, code, message)`.
- `models/` are the SQLAlchemy tables. `schemas/` are the request and response shapes. `core/` holds settings, constants, the time helper, security and error handlers.
- `get_db` gives each request one `Session`, rolls back on any exception and never commits.
- Every error response has the shape `{ "code": "...", "message": "..." }`.
- Schema changes go through a hand-written Alembic migration (`0001_initial`, `0002_manager_hierarchy`). `metadata.create_all` is never used, because it cannot create the overlap exclusion constraint.

### API

| Method and path | Who | Purpose |
|---|---|---|
| `GET /health` | public | Returns `{"status": "ok"}` |
| `POST /auth/signup` | public | Employee signup with the join code; returns a token and the user |
| `POST /auth/login` | public | Returns a token and the user |
| `GET /me` | any user | Profile, role and `manager_name` |
| `GET /balances` | any user | Own balances for the current year; creates missing rows |
| `POST /leave-requests` | any user except the super manager | Submit a request |
| `GET /leave-requests?status=` | any user | Own requests, newest first |
| `GET /leave-requests/{id}` | owner or any manager | Request detail. Not restricted by the hierarchy: any manager can open a manager's request by its id. For a manager viewer it also carries `employee_manager_name` (the requester's assigned manager, null if none); the owner's own view does not |
| `POST /leave-requests/{id}/cancel` | requester | Cancel a pending request |
| `POST /leave-requests/{id}/approve` | any manager for an employee's request; only the requester's manager for a manager's request. Never the requester | Approve, with an optional comment |
| `POST /leave-requests/{id}/reject` | any manager for an employee's request; only the requester's manager for a manager's request. Never the requester | Reject, with a required comment |
| `GET /manager/requests?status=` | manager | Pending queue and history, never including the caller's own requests or manager requests the caller cannot act on (so the super manager sees all employees and `manager1` and `manager2`; a normal manager sees employees only). Rows carry `requester_role` and `employee_manager_name` (the requester's assigned manager, null if none) |

### Frontend routes

| Route | Who | Screen |
|---|---|---|
| `/login`, `/signup` | public | Login and employee signup |
| `/dashboard` | any user except the super manager | Balance cards and the five newest requests. Managers reach it through "My leave", which the super manager does not see |
| `/requests/new` | any user except the super manager | New request form with a live working-day preview and the line "This request will be sent to: <manager name>" |
| `/requests` | any user except the super manager | Own requests with a status filter, a "Sent to" column, decision comments and Cancel on pending rows |
| `/requests/:id` | owner or manager | Detail (the super manager is sent to the queue for their own, which cannot exist). Shows "Sent to" for the owner and "Assigned manager" for a manager viewing someone else's request. Approve and Reject appear for a manager viewing someone else's pending request |
| `/manager/queue` | manager | Pending requests, oldest first, with an Assigned manager column and the employee's available balance |
| `/manager/history` | manager | Decided requests, filtered by status. A Requester column shows the name and an Employee or Manager tag, next to an Assigned manager column |

After login, employees land on `/dashboard` and managers on `/manager/queue`. The super manager has no leave of their own, so `/dashboard`, `/requests` and `/requests/new` redirect them to `/manager/queue`. A 401 from any call clears the token and redirects to `/login`, except for login and signup, whose errors are shown inline.

## 5. Data model

Enum-like values are stored as `VARCHAR` with `CHECK` constraints and are uppercase in the database and the API.

**`users`**

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity | primary key |
| `employee_code` | varchar(16) | unique, `EMP-0001` style, from the sequence `employee_code_seq` |
| `name` | varchar(100) | |
| `email` | varchar(254) | unique, `CHECK (email = lower(email))` |
| `password_hash` | text | Argon2 |
| `role` | varchar(16) | `EMPLOYEE` or `MANAGER`, default `EMPLOYEE` |
| `manager_id` | bigint | nullable FK to `users.id`, `ON DELETE SET NULL`, `CHECK (manager_id <> id)`. A manager with no manager is the super manager |
| `created_at` | timestamptz | default `now()` |

**`leave_balances`** (primary key `user_id, leave_type, year`)

| Column | Type | Notes |
|---|---|---|
| `user_id` | bigint | foreign key to `users` |
| `leave_type` | varchar(8) | `EARNED` or `SICK` |
| `year` | smallint | |
| `total_days` | smallint | the entitlement, taken from one constant: 12 Earned, 10 Sick |
| `used_days` | smallint | default 0; changes only when a request is approved |

**`leave_requests`**

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity | primary key |
| `user_id` | bigint | the requester, foreign key to `users` |
| `leave_type` | varchar(8) | `EARNED` or `SICK` |
| `start_date`, `end_date` | date | inclusive calendar dates |
| `days` | smallint | working days, computed on the server and stored |
| `reason` | varchar(500) | optional |
| `status` | varchar(16) | `PENDING`, `APPROVED`, `REJECTED` or `CANCELLED`, default `PENDING` |
| `decided_by` | bigint | foreign key to `users`, null until approved or rejected |
| `decided_at` | timestamptz | null until approved or rejected |
| `decision_comment` | varchar(500) | optional on approve, required on reject |
| `created_at` | timestamptz | default `now()` |

Key constraints, enforced by PostgreSQL itself:

- **No overlap:** `ex_leave_requests_no_overlap` is an exclusion constraint (`btree_gist`) on `user_id WITH =` and `daterange(start_date, end_date, '[]') WITH &&`, only for rows whose status is `PENDING` or `APPROVED`. A user cannot hold two overlapping live requests of any leave type. Rejected and cancelled requests never block a new one. The service turns a violation (SQLSTATE `23P01`) into 409 `OVERLAPPING_REQUEST`.
- **Balance range:** `ck_leave_balances_used_range` is `CHECK (used_days >= 0 AND used_days <= total_days)`, so `used` can never exceed the entitlement. A violation during approval becomes 409 `INSUFFICIENT_BALANCE`.
- **No self-approval:** `ck_leave_requests_not_self` is `CHECK (decided_by <> user_id)`. A null `decided_by` passes, which cancel relies on.
- Also on `leave_requests`: `end_date >= start_date`, `days > 0`, and checks on `leave_type` and `status`. Indexes cover `(user_id, status)`, `(status)` and `(start_date, end_date)`.

Balance formula, per user, leave type and year:

```
available = total - used - pending
```

`total` and `used` are stored. `pending` is never stored: it is the sum of `days` over the user's `PENDING` requests of that type, computed whenever it is needed. Pending days are therefore reserved against `available` as soon as a request is submitted, but `used` only changes when a request is approved.

## 6. Business rules as implemented

**Working days and time**

- Working days are Monday to Friday. Weekends are excluded and public holidays are ignored. Leave is counted in whole days only.
- "Today" and "the current year" come from one helper, `core/time.py::company_today()`, in the company timezone `Asia/Kolkata`.
- Entitlements come from one constant, `core/constants.py::ENTITLEMENTS` (Earned 12, Sick 10). Balance rows are created for the current year at signup, by the seed, by `GET /balances`, and just before they are locked in submit and approve. There is no carry-forward and no proration.

**Submitting a request.** The first rule that fails is returned, in this order:

| Rule | Status | Code |
|---|---|---|
| `end_date` before `start_date` | 422 | `INVALID_DATE_RANGE` |
| No working days in the range (for example Saturday to Sunday) | 422 | `NO_WORKING_DAYS` |
| Range spans two calendar years | 422 | `SPANS_MULTIPLE_YEARS` |
| Dates not in the current calendar year (past dates in the current year are allowed) | 422 | `NOT_CURRENT_YEAR` |
| Overlaps the user's own pending or approved request, of either leave type | 409 | `OVERLAPPING_REQUEST` |
| More days than `available` for that type | 409 | `INSUFFICIENT_BALANCE` |

A malformed body (wrong types, `reason` longer than 500 characters) is rejected first with 422 `VALIDATION_ERROR`.

**Who can do what**

- **Employee:** sign up, log in, view own balances, submit, list and view own requests, cancel own pending requests.
- **Manager:** everything an employee can, with their own balances and requests, plus the pending queue, history, and approve or reject on other people's requests. Any manager can act on any employee's request except their own, and the first action wins.
- **Manager hierarchy:** every user can have a manager (`manager_id`). A manager with no manager is the super manager (there is no extra role). An employee's request can be approved or rejected by any manager except the requester. A manager's request can be approved or rejected only by that manager's own manager (the super manager, for `manager1` and `manager2`); any other manager gets 403 `NOT_REQUESTERS_MANAGER`, after the self-action check and before the status check. The pending queue and history hide manager requests the viewer cannot act on. The request detail endpoint is the one exception: it stays open to any manager. The super manager cannot submit leave (403 `MANAGER_HAS_NO_MANAGER`). New signups get a random manager that has a manager of their own (`manager1` or `manager2` in the seed, never the super manager), or no manager if there is none, and `GET /me` returns `manager_name`.
- Only a pending request can be cancelled, and only by its requester (403 `FORBIDDEN` otherwise, then 409 `ALREADY_ACTIONED` if it is no longer pending). Approved, rejected and cancelled requests are final.
- Rejecting requires a non-blank comment (422 `COMMENT_REQUIRED`). The comment is optional when approving.
- A manager acting on their own request gets 403 `SELF_ACTION_FORBIDDEN`. That check runs before the status check.
- A request can be opened by its owner or by any manager, including a manager's request, which is not restricted to the requester's manager. Anyone else gets 403 `FORBIDDEN`.
- `GET /manager/requests` never returns the caller's own requests. Pending rows are oldest first and carry `employee_available`, the requester's available balance for that request's type and year (it already subtracts the request being reviewed, so the UI labels it "Available (after pending)"). Other filters are newest first.
- Role checks happen on the server. The role is read from the database row on every request, never from the token.

**Authentication**

- Passwords are at least 8 characters. Emails are lowercased on signup and login.
- The join code is compared with `SIGNUP_CODE` in constant time before anything else, so a wrong or missing code always gets the same generic 400 `SIGNUP_FAILED`. A duplicate email is 409 `EMAIL_ALREADY_REGISTERED`.
- The signup body has no role field; a role sent by a client is ignored and the user is always an employee.
- Login returns 401 `INVALID_CREDENTIALS` for an unknown email or a wrong password, and does the same hashing work in both cases.

**Concurrency.** All of it runs on PostgreSQL's default READ COMMITTED isolation, with explicit locks taken in one fixed order (advisory lock, then request row, then balance row):

- **Submit:** takes a per-user advisory lock (`pg_advisory_xact_lock`), so one user's submits are processed one at a time across both leave types. It then creates the balance row if missing, locks it with `SELECT ... FOR UPDATE`, checks overlap, checks the balance, and inserts.
- **Approve and reject:** lock the request row with `SELECT ... FOR UPDATE`, then the requester's balance row, then check self-action, then status. Two managers acting at once is decided by the request-row lock: the second sees the first one's result and gets 409 `ALREADY_ACTIONED`. Approve re-checks `used + days <= total` before incrementing.
- **Cancel:** locks the request row only. Cancel racing an approve is decided the same way, so exactly one succeeds.
- The exclusion constraint and the balance `CHECK` stay in place as backstops if any write path skipped an application check.
- The suite includes race tests that run each scenario 20 times behind a thread barrier and check the invariants afterwards (`0 <= used <= total`, no negative `available`, no overlapping live requests, `used` equals the sum of approved days).

## 7. Local setup

**Prerequisites:** Python 3.12, PostgreSQL 16 (13 or later is needed for `btree_gist` to be a trusted extension) and Node 20 or later. On macOS with Homebrew, Python and PostgreSQL are not on the default PATH:

```bash
export PATH=/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:$PATH
```

**1. Create the databases**

```bash
createdb leave        # development
createdb leave_test   # tests only: the suite migrates it and TRUNCATEs its tables
```

The migration runs `CREATE EXTENSION IF NOT EXISTS btree_gist` itself.

**2. Backend environment**

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Then edit `backend/.env`. `.env` is git-ignored; only `.env.example` is tracked.

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Development database, for example `postgresql+psycopg://localhost:5432/leave`. A `postgres://` or `postgresql://` URL is rewritten to the psycopg 3 driver automatically |
| `TEST_DATABASE_URL` | Test database. The suite refuses to run unless it points at a localhost database whose name ends in `_test` |
| `SECRET_KEY` | Required. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SIGNUP_CODE` | Required. The join code employees must enter to sign up |
| `PASSWORD_HASH_FAST` | Leave `false`. Only the test suite sets it, to make hashing cheap |
| `CORS_ORIGINS` | Comma-separated allowed browser origins. Default `http://localhost:5173` |

The app refuses to start without `SECRET_KEY` and `SIGNUP_CODE`.

**3. Migrate and seed**

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed     # safe to run twice; the second run reports 0 created
```

The seed creates the seven demo users from section 2 and their current-year balances, and sets every demo user's `manager_id`, including on users that already exist. It never changes an existing user's name, role or password.

**4. Run the backend**

```bash
.venv/bin/uvicorn app.main:app --reload
```

The API is at http://localhost:8000 and its docs at http://localhost:8000/docs.

**5. Run the tests** (from `backend/`; needs the `leave_test` database)

```bash
.venv/bin/pytest -q                      # everything: 446 tests
.venv/bin/pytest -q -m "not concurrency"
.venv/bin/pytest -q -m concurrency       # the race tests (147 of the 446)
```

**6. Run the frontend** (in a second terminal)

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_BASE_URL=http://localhost:8000
npm run dev              # http://localhost:5173
npm run build            # production build into frontend/dist
```

## 8. Deployment

There is no `render.yaml` or Docker file. Both Render services and the Neon database are configured by hand in their dashboards, with the settings below.

**Database: Neon.** A free PostgreSQL 16 database with `btree_gist` available. Its connection string goes into the API's `DATABASE_URL` as given, including `?sslmode=require`.

**API: Render web service** (free plan, Python)

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `alembic upgrade head && python -m scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

The free plan has no pre-deploy command, so the migration and the seed run in the start command on every start. Both are idempotent.

Environment variables (names only):

- `DATABASE_URL`: the Neon connection string
- `SECRET_KEY`: a random value different from the local one
- `SIGNUP_CODE`: the join code given to employees
- `CORS_ORIGINS`: the exact origin of the static site, scheme and host with no trailing slash
- `PYTHON_VERSION`: a full 3.12 version, to match local development
- `PASSWORD_HASH_FAST` is deliberately not set.

**Frontend: Render static site**

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm install && npm run build` |
| Publish directory | `dist` |
| Rewrite rule | `/*` to `/index.html`, so opening a client-side route such as `/dashboard` directly does not return a 404 |

Environment variable: `VITE_API_BASE_URL`, the public URL of the API with no trailing slash. Vite bakes it into the bundle at build time, so the site must be rebuilt if it changes.

## 9. Assumptions

1. One company and one fixed timezone, `Asia/Kolkata`. Dates are plain calendar dates with no time of day.
2. The leave year is the calendar year. Each user gets the full entitlement (12 Earned, 10 Sick) for it, with no proration and no carry-forward.
3. Pending days are reserved against `available` at submit time. `used` changes only on approval.
4. Any manager can act on any employee's request. A manager's own leave is approved only by their own manager (`manager_id`), and the super manager has no manager.
5. Past dates inside the current year are allowed for both leave types. Trust is placed in the manager's approval.
6. The year of a request is the year of its `start_date`. A request cannot span two years.
7. Cancelling is not a decision, so a cancelled request keeps `decided_by` and `decided_at` empty.
8. Rejecting an already-actioned request with a blank comment returns 409, not 422, because the status check comes before the comment check.
9. The weekend is Saturday and Sunday for everyone. There are no per-employee work patterns.
10. The join code is one shared value, given to employees outside the app.
11. HTTPS is handled by the host. Tokens are short-lived (60 minutes) and there are no refresh tokens.
12. The demo passwords in the seed script are for non-production use.

## 10. Known limitations

- **No holidays.** Public holidays count as working days. There are no half-days or hourly leave, and only the Earned and Sick types exist.
- **Email and passwords.** Email addresses must be ASCII only (non-ASCII characters such as accented letters are rejected), and there is no password reset or email verification.
- **Free-tier cold start.** The free Render backend sleeps when idle and the first request can take about a minute. The Neon database also suspends when idle.
- **No frontend automated tests.** The frontend is checked by building it and by hand. Only the backend has tests.
- **No admin UI.** Managers exist only through the seed script. There is no role promotion, user deactivation or manager reassignment.
- **An employee's manager is informational.** It is shown on screen (the New request form, My requests, the request detail, and the manager Queue and History) and in `/me`, but gives no priority: any manager can still act on the employee's requests, and nothing is routed or escalated to the assigned manager. A request is therefore "sent to" the assigned manager only in what the screens say.
- **The super manager cannot take leave.** With no manager, nobody could approve it, so submitting is refused with `MANAGER_HAS_NO_MANAGER`.
- **Shared join code.** One code for everyone, with no per-person invitations. There is no rate limiting on signup or login, so the code and passwords could be guessed by repeated attempts.
- **Token handling.** The JWT is kept in the browser's `localStorage` and cannot be revoked. After 60 minutes the user is sent back to the login page.
- **Approved leave is final.** It cannot be cancelled or revoked, and a submitted request cannot be edited (cancel and resubmit instead). Pending requests never expire.
- **Year rollover is lazy.** There is no `ensure-balances` command (it was cut from the plan). A new year's balance rows are created the first time a user's balances are loaded or a request is submitted or decided. Nothing carries forward. A pending request from a previous year stays actionable and uses that year's balance, although the dashboard shows only the current year.
- **No pagination.** Lists return every matching row, which suits a small organisation.
- **History "All".** The "All" filter on manager history asks the API for every status and then hides pending rows in the browser, because pending requests belong in the queue.
- **Hand-configured hosting.** Render settings live in the dashboards, not in a file in this repository, so the deployment cannot be recreated from the repo alone.
- **Tooling.** No linter is configured.

## 11. Possible improvements

- **Team-only visibility.** The assigned manager is only informational today. Managers would see and decide only their own team's requests, with the super manager as the backup when a manager is on leave.
- **Real notifications.** Email or chat messages when a request is submitted, approved or rejected, instead of checking the app.
- **Holidays calendar.** Public holidays would not count as working days.
- **Password reset.** A self-service reset flow, which needs email delivery.
- Monitoring and observability: metrics, request tracing and downtime alerts (today the app relies on Render's logs and structured error codes).

## 12. Project layout

```
README.md  SPEC.md  DESIGN.md  PLAN.md  NOTES.md  CLAUDE.md
backend/
  app/
    main.py                    app factory, CORS, routers, error handlers
    core/                      config, constants, time, security, errors
    db/                        engine and session, declarative base
    models/                    users, leave_balances, leave_requests
    schemas/                   request and response shapes
    services/                  auth, balances, leave requests, approval, working days
    routers/                   deps (get_db, get_current_user, require_manager),
                               auth, me, balances, leave_requests, manager, health
  alembic/                     env.py and versions/0001_initial.py, 0002_manager_hierarchy.py (hand-written)
  scripts/seed.py              idempotent seed
  tests/                       unit/, api/, concurrency/, conftest.py
  requirements.txt  pytest.ini  alembic.ini  .env.example
frontend/
  index.html  vite.config.js  package.json  .env.example
  src/
    main.jsx  App.jsx          router and layout
    api/                       client.js (the only fetch), endpoints.js
    auth/AuthContext.jsx       token, user, login, signup, logout, route guards
    pages/                     login, signup, dashboard, new request, my requests,
                               request detail, manager queue, manager history
    components/                NavBar, BalanceCards, LeaveRequestForm, RequestsTable,
                               StatusBadge, DecisionDialog, ErrorBanner
    utils/                     workingDays (preview only), labels, decisionErrors
```

`SPEC.md` says what the app does, `DESIGN.md` says how, `PLAN.md` gives the order of work, and `NOTES.md` records the toolchain, host and per-step notes.
