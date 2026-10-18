# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Leave management app for a small organisation. Source documents: `SPEC.md` (what), `DESIGN.md` (how), `PLAN.md` (order of work and exit gates), `NOTES.md` (toolchain, host, per-step explain-backs). The current step is the last '## Step' heading in NOTES.md.

## Working agreement

- One `PLAN.md` step at a time, in order. Do not start the next step.
- MUST tests first: write them before the application code, and make them pass.
- Never commit before the user's explain-back is written in `NOTES.md`.
- Never print, read, or commit secrets, and never open `backend/.env`. Only `.env.example` is tracked.

## Environment

Python 3.12 and PostgreSQL 16 are Homebrew installs that are not on the default PATH:

```bash
export PATH=/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:$PATH
```

Local databases: `leave` (dev) and `leave_test` (tests). `tests/conftest.py` refuses to run unless `TEST_DATABASE_URL` points at a localhost database whose name ends in `_test`, because the suite migrates and TRUNCATEs it.

## Commands (run from `backend/`)

```bash
# install
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # then set SECRET_KEY and SIGNUP_CODE; .env is git-ignored

# database
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade base
.venv/bin/alembic check         # reports drift between models and the migrated DB

# run
.venv/bin/uvicorn app.main:app --reload

# test (needs the leave_test database; the suite migrates it itself)
.venv/bin/pytest -q
.venv/bin/pytest tests/api/test_db_constraints.py::test_d3_decided_by_equal_to_user_id_is_rejected -q   # single test
.venv/bin/pytest -q -m "not concurrency"
.venv/bin/pytest -q -m concurrency
```

No linter is configured yet.

## Architecture

`routers/` (HTTP only) → `services/` (rules, locks, the single `commit()`) → `models/` → PostgreSQL. Layer rules are in `DESIGN.md` §1.3.

- **Transactions:** `routers/deps.py::get_db` yields one `Session` per request, rolls back on any exception and never commits. Services commit exactly once, as their last step.
- **Errors:** services raise `AppError(status, code, message)`; handlers in `core/errors.py` render `{code, message}`.
- **Schema:** changes go through hand-written Alembic migrations, never `metadata.create_all`. The overlap exclusion constraint `ex_leave_requests_no_overlap` exists only in the migration, and `alembic/env.py::include_object` hides it from autogenerate.
- **Constants:** entitlements come from `core/constants.py::ENTITLEMENTS` only; "today" comes from `core/time.py::company_today()` only.
- **Tests:** `tests/conftest.py` sets `PASSWORD_HASH_FAST` and `DATABASE_URL` (= `TEST_DATABASE_URL`) before importing the app, migrates once per session, and truncates between tests (including restarting `employee_code_seq`).
