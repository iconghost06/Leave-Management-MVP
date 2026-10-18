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
