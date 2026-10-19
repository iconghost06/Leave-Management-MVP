# Notes

## Phase 0

### Toolchain

- Python 3.12
- Node 24
- PostgreSQL 16 (Homebrew)
- Local databases: `leave` and `leave_test`
- `btree_gist` extension verified locally

### Host

- Render: free web service for the API, free static site for the frontend
- Neon: free Postgres, version 16
- `btree_gist` extension verified on the hosted database

### Free-tier limits

- Render web service: spins down after 15 min idle, about 1 min cold start,
  750 free hours per month
- Neon: compute suspends after 5 min idle, 1 GB storage, no expiry on the
  free plan

## Step 1.1

_Summary written by Claude Code, to be replaced with my own words._

- Built the FastAPI backend skeleton: settings from environment variables, the layered layout (`routers` → `services` → `models`), the `AppError` handlers that render `{code, message}`, and `GET /health`.
- `get_db` gives each request one `Session`, rolls back on any exception and never commits. Services commit once, as their last step.
- Added the three models (users, leave balances, leave requests) and one hand-written Alembic migration, `0001`. It creates `btree_gist` first, then the tables with their CHECK constraints and indexes. The overlap exclusion constraint `ex_leave_requests_no_overlap` is written with `op.execute`, because autogenerate cannot express it. `env.py::include_object` hides it so autogenerate never tries to drop it. `metadata.create_all` is never used.
- The test harness refuses to run unless `TEST_DATABASE_URL` is a localhost database whose name ends in `_test`. It migrates once per session, then truncates every table between tests (restarting identities and `employee_code_seq`, which `RESTART IDENTITY` does not reset). `PASSWORD_HASH_FAST` and `DATABASE_URL` are set before the app is imported.
- Tests D1, D2, D3 and H1 prove the database backstops: the used-days range, the overlap exclusion, the no-self-decision CHECK, and the health endpoint.

## Step 1.2

_Summary written by Claude Code, to be replaced with my own words._

- Added signup, login and `GET /me`. A token is minted at login and checked by `get_current_user`, which then loads the user row from the database.
- The role is always read from that database row, never from the token, so a forged or out-of-date `role` claim cannot make someone a manager (R14, R22).
- Signup checks the join code first, in constant time, before any validation or database access, so a wrong or missing code gets the same `SIGNUP_FAILED` body and nobody can probe emails (A2). The signup schema has no `role` field, so a role sent by the client is dropped and new users are always EMPLOYEE (A3). Emails are lowercased on signup and login (A5).
- The seed is the only way a manager is created. It checks each email before inserting and never edits existing users, so a second run creates nothing (E1, E2, R23). Each user also gets 12 Earned + 10 Sick balance rows through `ensure_balance_rows`.

## Step 1.3

_Summary written by Claude Code, to be replaced with my own words._

- `core/config.py` now accepts a `DATABASE_URL` that starts with `postgres://` or `postgresql://` and rewrites only that prefix to `postgresql+psycopg://`, so SQLAlchemy uses psycopg 3. The rest of the URL, including `?sslmode=require`, is untouched. A URL that already names the driver is left alone. The app and Alembic both read `settings.database_url`, so one rewrite covers both. `tests/unit/test_config.py` covers it.
- `backend/.env.example` has production notes: where each variable comes from, and the build and start commands. No real values.
- No Docker files and no `render.yaml`. The service is configured by hand in the Render dashboard, using the values below.

| Render setting | Value |
|---|---|
| Service type | Web Service, free plan |
| Language / runtime | Python 3 |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| `PYTHON_VERSION` | `3.12.15` (a full version, matching local) |
| `DATABASE_URL` | the Neon connection string, as given (with `?sslmode=require`) |
| `SECRET_KEY` | a new random value, generated for production |
| `SIGNUP_CODE` | the join code chosen for production |
| `PASSWORD_HASH_FAST` | not set |
| `CORS_ORIGINS` | not needed until the frontend is deployed |

- The migration runs in the start command because the free tier has no pre-deploy command. The seed is not run until step 4.4.

## Step 2.1

_Summary written by Claude Code, to be replaced with my own words._

- `count_working_days(start, end)` counts the Mon–Fri dates in the range, both ends included. A weekend at either end adds nothing, so Fri→Mon is 2 and Sat→Sun is 0. Holidays are not looked at (R4; U1–U4).
- `validate_dates(start, end)` returns `(days, year)` or raises `AppError(422, …)` for the first rule that fails, in SPEC §6 order: `INVALID_DATE_RANGE`, `NO_WORKING_DAYS`, `SPANS_MULTIPLE_YEARS`, `NOT_CURRENT_YEAR`. The order is part of the contract, so U9 feeds it inputs that break several rules at once (R5–R8, R11).
- "Today" comes only from `core.time.company_today()`, through `current_year()`, which uses the Asia/Kolkata date and not the server's UTC date. Tests freeze that one function, and U11 shows 19:00Z on 31 Dec is already 1 Jan in IST (R24).
- No database and no endpoints in this step. Backdating inside the current year is allowed (U10); the balance and overlap checks come later, in `submit_request`.

## Step 2.2

_Summary written by Claude Code, to be replaced with my own words._

- `submit_request` checks the dates first, then takes locks in one fixed order: the per-user advisory lock (serialises all of one user's submits, both leave types), then `ensure_balance_rows`, then `FOR UPDATE` on the balance row (approve changes `used_days` without the advisory lock), then the overlap check, then the balance check, then the insert. The balance year is `start_date.year` (Q11). A test records the SQL and fails if that order changes (R9, R10, R12; S1–S10).
- `available = total − used − pending`, where `pending` is the SUM of the user's PENDING `days` for that type and year and is never stored (R3). `GET /balances` creates missing current-year rows, so it commits once (R2; B2).
- Overlap is checked in the app first, which gives the specific 409. If a write path skips that check, the exclusion constraint raises SQLSTATE `23P01` on the insert and the service turns it into the same 409 `OVERLAPPING_REQUEST`, so it is never a 500 (R9; D2, S4–S6).
- `cancel_request` locks the request row, checks ownership (403) before status (409), and leaves `decided_by` and `decided_at` NULL, because a cancel is not a decision and the CHECK forbids the requester as `decided_by` (Q3, Q14, R13; C1–C4). Detail is allowed for the owner or any manager (R20, Q13). No approve, reject or manager endpoint exists yet; `decided_by_name` and B1 arrive in step 3.1.

## Step 3.1

_Summary written by Claude Code, to be replaced with my own words._

- `approve_request` and `reject_request` share one prologue: lock the request row, then the requester's balance row (reject locks it too, Q4), then check the caller is not the requester (403 `SELF_ACTION_FORBIDDEN`), then check the status is PENDING (409 `ALREADY_ACTIONED`). Self comes before status so a manager gets 403 even on their own already-actioned request (R15, R16; P4, P5, P6).
- Approve re-checks `used + days <= total` (409 `INSUFFICIENT_BALANCE`) and then adds the days to `used`. If that check were ever bypassed, the `ck_leave_balances_used_range` CHECK raises `23514`, which maps to the same 409 (R17; P1, P8). Reject needs a non-blank comment, and that 422 `COMMENT_REQUIRED` is only reachable once the request is PENDING (Q5, R18; P2, P7). The role gate (`require_manager`) runs first and returns 403 `FORBIDDEN` (R14; P3). Another manager can approve a manager's request (P9).
- Responses now carry `decided_by_name`, through a `decider` relationship that is an outer join (PENDING and CANCELLED rows have no decider). B1 runs the real submit, approve and reject flow and checks used, pending and available at each step (R3).
- The race harness runs each racing call in its own thread with its own Session, behind a `Barrier` with a timeout. An `AppError` counts as its status, any other exception counts as a 500 and fails the test, a hang fails instead of blocking, and the invariants (`0 <= used <= total`, `available >= 0`, no overlapping PENDING/APPROVED rows, `used` = sum of APPROVED days) are checked after every run. X1–X6 (and X7) run 20 times each. Removing the request-row lock makes X1 fail on the invariant check, so the tests can go red. X5 shows the right outcome but cannot prove the advisory lock is what prevents a `40P01`, because that window is too small to hit on demand; the lock itself is pinned by the SQL-order test in `test_submit.py`.

## Step 3.2

_Summary written by Claude Code, to be replaced with my own words._

- `GET /manager/requests` sits behind `require_manager`, so an employee gets 403 `FORBIDDEN` and a missing token gets 401. The service adds `WHERE user_id != caller.id` to every query, whatever the status filter. That is how a manager never sees their own requests, while another manager does and can approve them (R19; V1, V2, P9).
- PENDING rows are sorted by `created_at` ascending, oldest first, so the queue works through requests in the order they came in. Every other filter, or no filter at all, is `created_at` descending, newest first, with `id` as a tie-break (Q7, Q8; V1, V2).
- `employee_available` is set on PENDING rows only and is null otherwise. For each row it is `total − used − pending` for that requester, leave type and the year of `start_date` (R3). It is worked out for the whole page with two queries, one for balance rows and one grouped sum of PENDING days, and not one query per row. The figure already includes the request under review, which is why the UI will label it "Available (after pending)" (Q6; V1).
- This is the last backend step, so the backend is frozen and tagged `backend-freeze`. `app/cli.py ensure-balances` was skipped as cut-list item 1, because `GET /balances`, signup, seed, submit and approve already create balance rows lazily (R2). That cut goes in the README limitations. The full suite (344 tests, concurrency included) is green.

## Step 3.3

_Summary written by Claude Code, to be replaced with my own words._

- The `postgres://` / `postgresql://` to `postgresql+psycopg://` rewrite and its tests (`tests/unit/test_config.py`) were already added in step 1.3, so no code changed here. The rewrite keeps `?sslmode=require`. `backend/.env.example` already lists `DATABASE_URL`, `SECRET_KEY`, `SIGNUP_CODE` and `CORS_ORIGINS`, with placeholders only.
- No Docker files and no `render.yaml`. The service is set up by hand in the Render dashboard with these settings:

| Render setting | Value |
|---|---|
| Service type | Web Service, free plan |
| Language / runtime | Python 3 |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| `PYTHON_VERSION` | `3.12.15` (a full version, matching local) |
| `DATABASE_URL` | the Neon connection string, as given (with `?sslmode=require`) |
| `SECRET_KEY` | a new random value, generated for production |
| `SIGNUP_CODE` | the join code chosen for production |
| `CORS_ORIGINS` | the deployed frontend origin, no trailing slash; not needed until the frontend is deployed |
| `PASSWORD_HASH_FAST` | not set |

## Step 4.2

_Summary written by Claude Code, to be replaced with my own words._

- `frontend/` is a plain-JS Vite app with react-router v6 and one stylesheet (`src/index.css`), and no UI, state or test library. `api/client.js` is the only file that calls `fetch`. It reads `VITE_API_BASE_URL` (default `http://localhost:8000`), adds the `Authorization: Bearer` header from `localStorage`, and throws `ApiError{status, code, message}` for any non-2xx response.
- On a 401, `client.js` clears the token and calls a handler that AuthContext registers, which drops the user and navigates to `/login`. `POST /auth/login` and `POST /auth/signup` are the only exceptions. Their 401 `INVALID_CREDENTIALS` and 400 `SIGNUP_FAILED` are thrown to the page and shown inline in `ErrorBanner`, so a wrong password does not reload the login page and hide the message (DESIGN §1.3, §7).
- AuthContext holds the user, calls `/me` once on boot when a token exists, and exposes `login`, `signup`, `logout` and `role`. The role comes from `/me`, which reads the DB row, never from the token (§6.1). `RequireAuth` checks the stored token on every render, so removing it in devtools redirects to `/login` on the next navigation. `RequireManager` sends employees to `/dashboard`. Both are UX only, and the server enforces every rule.
- The login button shows "Signing in..." while waiting, and a timer adds "The server may be waking up, please wait." after 5 s for free-tier cold starts. After login, employees go to `/dashboard` and managers to `/manager/queue`, both placeholder pages. The backend suite (344 tests) is green and `npm run build` succeeds. The browser checklist from PLAN 4.2 has not been run yet.

## Step 4.3

_Summary written by Claude Code, to be replaced with my own words._

- The employee screens are `/dashboard` (balance cards from `GET /balances` plus the 5 newest requests), `/requests/new`, `/requests` and `/requests/:id`. Pages fetch through `api/endpoints.js` and keep `data`, `error` and `loading` state. Components (`BalanceCards`, `RequestsTable`, `StatusBadge`, `LeaveRequestForm`) only render from props, as in DESIGN §1.3.
- The form shows a live working-day count from `utils/workingDays.js` (Mon–Fri inclusive, holidays ignored, same as R4). It is only a preview: the server counts again on submit and is the authority. A server error is shown by its code. The four date codes (`INVALID_DATE_RANGE`, `NO_WORKING_DAYS`, `SPANS_MULTIPLE_YEARS`, `NOT_CURRENT_YEAR`) appear under the date fields, and everything else (`OVERLAPPING_REQUEST`, `INSUFFICIENT_BALANCE`, ...) appears in the banner above the form. Success redirects to `/requests`.
- `/requests` lists the user's requests with status badges and decision comments, and has a status filter. Cancel appears only on PENDING rows (R13). The page asks for a `window.confirm`, calls `POST /leave-requests/{id}/cancel`, then bumps a reload counter so the load effect refetches the list; a 409 is shown in the banner and the list is refreshed anyway. Every page shows "Loading..." while waiting, and the lists show "No requests yet" when empty.
- `/requests/:id` shows one request, and a 403 or 404 from the server is shown as a message (R20). The backend suite (344 tests) is green and `npm run build` succeeds. The browser checklist from PLAN 4.3 has not been run yet.

## Step 4.4

_Summary written by Claude Code, to be replaced with my own words._

- The frontend deploys as a static site: build command `npm install && npm run build`, publish directory `dist`, root directory `frontend`, plus an SPA rewrite from `/*` to `/index.html` so that opening a client-side route such as `/dashboard` directly does not return a 404.
- Static site environment variable: `VITE_API_BASE_URL`, set to the backend's public URL with no trailing slash. Vite bakes it into the bundle at build time, so changing it needs a rebuild. `npm run build` with `https://example.invalid` succeeds and that URL ends up in the bundle.
- Backend environment variable: `CORS_ORIGINS`, set to the static site's exact origin (scheme and host, no trailing slash). The backend splits it on commas, so several origins are allowed, and it never uses `*`. The default is `http://localhost:5173`.
- `frontend/.env.example` holds `VITE_API_BASE_URL=http://localhost:8000` and is the only tracked env file, because `frontend/.env` is git-ignored. Neither variable's real value is recorded here. The backend start command gains `python -m scripts.seed` between the migration and `uvicorn`, which is a host setting, not a code change.
