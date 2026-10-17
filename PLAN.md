# Leave Management MVP: Build Plan

Inputs: `SPEC.md` (what) and `DESIGN.md` (how). This file decides **in what order** the work is done and **when a phase counts as finished**.
Rule IDs (R#), test IDs (U/A/B/S/C/P/V/D/E/H/X) and decisions (Q#) refer to DESIGN.md.

> **Deadline:** Tue 20 Oct 2026, 17:00. **Developer:** solo, new to React.

---

## Ground rules

1. **One phase at a time, one step at a time, in order.** A step is done when its MUST tests pass, its verification command succeeds, its explain-back is written, and it is committed and pushed. Never start the next step on a red suite.
2. **Exit gates are hard.** Do not start the next phase until every box in the current phase's exit gate is ticked.
3. **MUST tests before SHOULD tests** (DESIGN §8). Write SHOULD tests only once every MUST test in the step passes.
4. **The backend freezes at the end of Phase 3.** After that, change the backend only to fix bugs the frontend exposes.
5. **Every commit leaves the app runnable.** Something can always be demoed.
6. **Explain-back after every step.** Before committing, have Claude Code quiz you on the diff (`git diff --staged`): it asks questions about the changed lines and you answer them. Claude Code only asks; it does not write the bullets. Then write 3–5 bullets yourself, in your own words, in `NOTES.md` under a `## Step X.Y` heading: what changed, why it is shaped that way, and which rule or test it serves. Commit `NOTES.md` with the step. If you cannot explain a line, you do not own it yet: reread it before moving on.

## Phases at a glance

| Phase | Name | Steps | Ends with |
|---|---|---|---|
| 0 | Setup | 0.1 toolchain + local DBs · 0.2 host + `btree_gist` | Toolchain works, host chosen, `btree_gist` proven on hosted DB |
| 1 | Foundation | 1.1 scaffold + migration · 1.2 auth + seed · 1.3 deploy skeleton | Auth works locally; bare backend live with `/health` and migrated hosted DB |
| 2 | Leave rules | 2.1 working days + `validate_dates` · 2.2 submit / cancel + balances | Employee leave flow works over curl |
| 3 | Approval and safety | 3.1 approve / reject + concurrency · 3.2 manager endpoints | Full backend suite green, **backend freeze** |
| 4 | Employee UI | 4.1 React warm-up · 4.2 React shell + login · 4.3 employee screens · 4.4 frontend deploy | Employee flow works in the browser; static site live and login works against the live API |
| 5 | Manager UI | 5.1 manager screens + acceptance flow | SPEC §12 acceptance flow passes in the browser |
| 6 | Ship | 6.1 full redeploy · 6.2 README + fresh clone · 6.3 submission · 6.4 demo | Live, documented, submitted, rehearsed |

---

## Phase 0: Setup

Removes the two risks that would otherwise show up late: a missing local toolchain, and `btree_gist` not being available on the host (DESIGN §9.2).

### Step 0.1: Toolchain and local databases

**Goal:** Every tool the build needs runs locally, and the dev and test databases exist.

- Install Python 3.12, Node 20+, PostgreSQL 16.
- Create two databases: `leave` (dev) and `leave_test` (tests).

**Verify**
```bash
python3.12 --version && node --version && psql --version
psql -d leave -c 'select 1' && psql -d leave_test -c 'select 1'
psql -d leave -c 'create extension if not exists btree_gist' -c '\dx'
```

**Explain-back:** versions installed, how you connect to each database, and what `btree_gist` is for (the overlap exclusion constraint, R9).

### Step 0.2: Choose host and verify `btree_gist` on the hosted DB

**Goal:** A host is chosen and its managed PostgreSQL is proven to support the extension the migration depends on.

- Choose a host that offers managed PostgreSQL ≥ 13, a Python web service and a static site (for example Render or Railway).
- Create the hosted database now. Put its external connection string in a local, uncommitted `.env` only.
- Run `CREATE EXTENSION IF NOT EXISTS btree_gist;` against it once by hand. If that fails, choose another host now (see **If the host fails** below).
- Check the free-tier limits you will hit later: whether a pre-deploy command is available, spin-down/cold-start behaviour, and the database expiry date.
- In `NOTES.md`, record **only** the host name and the database expiry date. **Never** write the connection string, or any part of it (host, user, password), into `NOTES.md` or any other tracked file.

**Verify**
```bash
psql "$HOSTED_DATABASE_URL" -c 'create extension if not exists btree_gist' -c '\dx'   # btree_gist listed
```

**Explain-back:** which host and why, and the `\dx` result. No connection string.

**Commit:** `docs: record toolchain and host choice in NOTES.md`

### Exit gate: Phase 0

- [ ] Python 3.12, Node 20+ and PostgreSQL 16 respond to `--version`.
- [ ] `leave` and `leave_test` exist and accept connections.
- [ ] `\dx` on the **hosted** database lists `btree_gist`.
- [ ] Host chosen; host name and DB expiry date written in `NOTES.md`, with no connection string anywhere in tracked files.
- [ ] Commit pushed.

---

## Phase 1: Foundation

### Step 1.1: Project scaffold + DB + migration

**Goal:** The backend skeleton boots. `alembic upgrade head` builds the full schema, with every constraint, on the dev and test databases. The test harness migrates once and truncates between tests. The DB-level backstops are proven.

**Files touched**
- `.gitignore`, `CLAUDE.md` (install/run/test commands)
- `backend/requirements.txt`, `backend/.env.example`, `backend/pytest.ini` (registers the `concurrency` marker)
- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_initial.py`
- `backend/app/main.py`, `app/core/config.py`, `app/core/constants.py`, `app/core/time.py`, `app/core/errors.py`
- `backend/app/db/session.py`, `app/db/base.py`
- `backend/app/models/user.py`, `leave_balance.py`, `leave_request.py`
- `backend/app/routers/deps.py` (`get_db` only), `app/routers/health.py`
- `backend/tests/conftest.py`, `tests/api/test_db_constraints.py`, `tests/api/test_health.py`

**Implements:** DESIGN §1.1 (transaction convention, `get_db`), §1.2 (layout), §2.1 (tables, constraints, indexes), §2.3 (migration notes), §6.4 (env vars), §8 (test infrastructure), §5 error shape and Q1 (`VALIDATION_ERROR` handler). Constants and helper for R1 (`ENTITLEMENTS`) and R24 (`company_today`). DB backstops for R9 (exclusion), R15 (`ck_leave_requests_not_self`) and R17 (`ck_leave_balances_used_range`).

**Tests that must pass**
- MUST: D1, D2, D3
- SHOULD: H1

**Watch out for**
- `requirements.txt` must list `psycopg[binary]`, not plain `psycopg`. The plain package needs a system libpq, which the host may not have.
- The migration's first statement creates `btree_gist`. Add the exclusion constraint with `op.execute`. Add `include_object` in `env.py` so autogenerate never drops it. Never use `metadata.create_all`.
- `TRUNCATE … RESTART IDENTITY` does **not** reset the standalone `employee_code_seq`. The test reset fixture must restart it too, or A1's `EMP-0001` assertions will drift.
- `conftest.py` must set `PASSWORD_HASH_FAST=true` and `DATABASE_URL=TEST_DATABASE_URL` **before** importing the app.

**Verify**
```bash
cd backend
alembic upgrade head && alembic downgrade base && alembic upgrade head
psql -d leave -c '\d leave_requests'          # shows ex_leave_requests_no_overlap and the 3 CHECKs
pytest tests/api/test_db_constraints.py tests/api/test_health.py -q
```

**Explain-back:** how a request gets a DB session and when it rolls back; why the exclusion constraint is hand-written; what the test reset fixture truncates and restarts.

**Commit:** `feat(db): scaffold FastAPI backend and initial migration with constraints`

### Step 1.2: Auth + seed

**Goal:** Employees can sign up with the join code, and anyone can log in and call `/me`. Managers and demo employees exist through an idempotent seed. Each of these users gets 12 Earned + 10 Sick rows.

**Files touched**
- `backend/app/core/security.py`
- `backend/app/schemas/auth.py`, `schemas/user.py`, `schemas/error.py`
- `backend/app/services/auth_service.py`, `services/balance_service.py` (`ensure_balance_rows` only)
- `backend/app/routers/deps.py` (`get_current_user`, `require_manager`), `routers/auth.py`, `routers/me.py`, `app/main.py` (register routers)
- `backend/scripts/__init__.py`, `backend/scripts/seed.py`
- `backend/tests/api/test_auth.py`, `tests/api/test_seed.py`, `tests/unit/test_security.py`

**Implements:** DESIGN §6.1 (JWT flow), §6.2 (signup), §6.3 (seed), §5 rows `/auth/signup`, `/auth/login`, `/me`, §1.3 (deps). Rules R1, R2 (signup and seed paths), R14 (the `require_manager` dependency; tested in step 3.1), R21, R22, R23. Decisions Q1, Q2, Q10, Q12.

**Tests that must pass**
- MUST: A1, A2, A3, A5, A7, E1, E2
- SHOULD: A4, A6, U12

**Watch out for**
- Check the join code first, with `hmac.compare_digest`, before touching the DB. Wrong and missing codes must return byte-identical bodies (A2).
- The signup schema has **no** `role` field and uses `extra="ignore"`. That is what makes A3 pass.
- `get_current_user` reads the role from the DB row, never from the token claim.
- A5: lowercase the email on **both** signup and login. A7 needs an expired token; mint one in the test with a past `exp` rather than waiting.

**Verify**
```bash
cd backend
pytest tests/api/test_auth.py tests/api/test_seed.py tests/unit/test_security.py -q
python -m scripts.seed && python -m scripts.seed   # second run reports 0 created
uvicorn app.main:app --reload                      # then log in as manager1 at http://localhost:8000/docs
```

**Explain-back:** the path of a token from login to `get_current_user`; why role comes from the DB row; why the join-code check runs first; what makes the seed idempotent.

**Commit:** `feat(auth): add signup, login, /me, JWT deps and idempotent seed`

### Step 1.3: Deploy skeleton

**Goal:** The bare backend runs on the chosen host. `GET /health` answers over HTTPS, and the hosted database has been migrated by the deploy itself. This proves the deploy path while the app is still small, so Phase 6 is a redeploy, not a first deploy. No frontend and no seed yet (both arrive in step 4.4).

**Files touched**
- Host config (for example `render.yaml`): backend web service and database only
- Python version pin for the host (for example `PYTHON_VERSION=3.12.x` in the host config, or a `.python-version` file), matching the local 3.12
- `backend/app/core/config.py` (accept the host's `postgres://` URL and rewrite it to `postgresql+psycopg://`)
- `backend/.env.example` (production notes)

**Implements:** DESIGN §6.4 (environment variables), §9.2 (`btree_gist` on the hosted DB), SPEC §13 assumption 10 (HTTPS handled by the host). No business rules.

- Python: pin the host to 3.12, the same version as local. Do not rely on the host's default Python.
- Build: `pip install -r requirements.txt`.
- Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` (free tiers usually have no pre-deploy command, so the migration runs in the start command). Step 4.4 adds the seed to this command.
- Environment: a new random `SECRET_KEY`, a `SIGNUP_CODE`, and `DATABASE_URL` from the hosted database. The app refuses to start without the first two.

**Tests that must pass**
- MUST: the full local `pytest -q` suite stays green.
- Live: `/health` returns 200, and the hosted schema has the exclusion constraint.

**Verify**
```bash
# build log on the host shows Python 3.12.x
curl -fsS https://<api-host>/health                                  # {"status":"ok"}
psql "$HOSTED_DATABASE_URL" -c '\d leave_requests'                   # ex_leave_requests_no_overlap present
psql "$HOSTED_DATABASE_URL" -c 'select version_num from alembic_version'   # 0001
```

**Explain-back:** what the host runs at build and at start; why the host's Python is pinned; why the migration lives in the start command; where each env var comes from; how the `postgres://` rewrite works.

**Commit:** `chore(deploy): deploy backend skeleton with /health and hosted migration`

### Exit gate: Phase 1

- [ ] `pytest -q` green, including D1–D3, A1, A2, A3, A5, A7, E1, E2.
- [ ] `alembic upgrade head && alembic downgrade base && alembic upgrade head` runs clean locally.
- [ ] curl, local: signup with the right code → 201; with a wrong code → 400 `SIGNUP_FAILED`; login → token; `GET /me` with the token → user with the correct role.
- [ ] Seed run twice locally; the second run reports 0 created.
- [ ] curl, live: `https://<api-host>/health` → `{"status":"ok"}`; hosted `alembic_version` is `0001`.
- [ ] Three commits pushed; `NOTES.md` has explain-back bullets for 1.1–1.3.

---

## Phase 2: Leave rules

### Step 2.1: Working days + date validation

**Goal:** These are pure functions with no DB: `count_working_days`, and `validate_dates` returning the first failing code in SPEC §6 order.

**Files touched**
- `backend/app/services/working_days.py`
- `backend/app/services/leave_request_service.py` (`validate_dates` only)
- `backend/app/core/time.py` (finalise `company_today`, `current_year`)
- `backend/tests/unit/test_working_days.py`, `tests/unit/test_validate_dates.py`, `tests/unit/test_time.py`

**Implements:** DESIGN §3 rules R4, R5, R6, R7, R8, R11 (date part), R24, and §4.1 step 1.

**Tests that must pass**
- MUST: U1, U2, U3, U4, U5, U6, U7, U8, U9
- SHOULD: U10, U11

**Watch out for**
- Order: `INVALID_DATE_RANGE` → `NO_WORKING_DAYS` → `SPANS_MULTIPLE_YEARS` → `NOT_CURRENT_YEAR`. U9 exists to catch a wrong order.
- `validate_dates` gets "today" from `core.time` only, so tests can monkeypatch one place.

**Verify**
```bash
cd backend && pytest tests/unit -q
```

**Explain-back:** how the working-day count handles a range that starts or ends on a weekend; why the error order matters; why "today" has exactly one source.

**Commit:** `feat(leave): add working-day count and date validation rules`

### Step 2.2: Submit / cancel + balances

**Goal:** Employees can submit, list, view and cancel their own requests, and see correct entitlement, used, pending and available figures. Submit runs in one transaction behind the per-user advisory lock.

**Files touched**
- `backend/app/services/balance_service.py` (`lock_balance`, `pending_days`, `get_balance_summary`)
- `backend/app/services/leave_request_service.py` (`submit_request`, `cancel_request`, `list_own_requests`, `get_request_for_viewer`)
- `backend/app/schemas/balance.py`, `schemas/leave_request.py` (`LeaveRequestIn`, `LeaveRequestOut`)
- `backend/app/routers/balances.py`, `routers/leave_requests.py`, `app/main.py`
- `backend/tests/conftest.py` (fixtures: seeded users, auth headers, frozen "today" in 2026)
- `backend/tests/api/test_balances.py`, `test_submit.py`, `test_cancel.py`, `test_views.py`

**Implements:** DESIGN §4.1 (submit, steps 0–8), §4.4 (cancel), §2.1 (SQLSTATE mapping `23P01` → 409), §5 rows `/balances`, `POST/GET /leave-requests`, `/leave-requests/{id}`, `/cancel`. Rules R2, R3, R9, R10, R11, R12, R13, R20. Decisions Q3, Q11, Q13, Q14.

**Tests that must pass**
- MUST: B2, S1, S2, S3, S4, S5, S6, S7, S8, S9, S10, C1, C2, C3, C4
- SHOULD: V3, V5, V4 (requester fields only; approver name comes in step 3.1)
- B1 is completed in step 3.1, because it needs approve.

**Watch out for**
- Lock order in submit: advisory lock, then `INSERT … ON CONFLICT DO NOTHING`, then the balance row `FOR UPDATE`, then the overlap check, then the balance check, then insert.
- The balance year is `start_date.year`, not "today's" year (Q11).
- Cancel checks ownership (403) **before** status (409) (Q14). `decided_by` and `decided_at` stay NULL (Q3).
- S4/S5 and C3 need APPROVED rows before approve exists. Set the status with direct SQL in the test fixture.

**Verify**
```bash
cd backend && pytest -q -m "not concurrency"
```

**Explain-back:** the lock order in submit and what each lock protects; how `available` is computed (R3); what turns a `23P01` into a 409; why cancel checks ownership before status.

**Commit:** `feat(leave): submit, cancel, list and balance endpoints with advisory-lock submit`

### Exit gate: Phase 2

- [ ] `pytest -q -m "not concurrency"` green, including U1–U9, B2, S1–S10, C1–C4.
- [ ] curl, local (as employee1, with `uvicorn` running and the seed applied):
  ```bash
  TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
    -d '{"email":"employee1@example.com","password":"Employee@123"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
  H="Authorization: Bearer $TOKEN"
  curl -s -X POST localhost:8000/leave-requests -H "$H" -H 'Content-Type: application/json' \
    -d '{"leave_type":"EARNED","start_date":"2026-11-02","end_date":"2026-11-06"}'   # 201, days 5
  # same POST again                                                                 # 409 OVERLAPPING_REQUEST
  curl -s -H "$H" localhost:8000/balances                                           # EARNED pending 5, available 7
  curl -s -X POST -H "$H" localhost:8000/leave-requests/<id>/cancel                 # status CANCELLED
  curl -s -H "$H" localhost:8000/balances                                           # EARNED available back to 12
  ```
- [ ] A Sat–Sun submit returns 422 `NO_WORKING_DAYS`.
- [ ] Two commits pushed; explain-back bullets for 2.1–2.2 in `NOTES.md`.

---

## Phase 3: Approval and safety

### Step 3.1: Approve / reject + concurrency tests

**Goal:** Managers can approve and reject with correct locking. Every race in SPEC §12 is proven safe under 20 repetitions, with no 500s and no deadlocks.

**Files touched**
- `backend/app/services/approval_service.py` (`approve_request`, `reject_request`)
- `backend/app/schemas/leave_request.py` (`DecisionIn`, `decided_by_name` on output)
- `backend/app/routers/leave_requests.py` (approve and reject routes)
- `backend/tests/api/test_approve_reject.py`, `tests/api/test_balances.py` (B1)
- `backend/tests/concurrency/conftest.py` (barrier harness and invariant checker)
- `backend/tests/concurrency/test_approval_races.py`, `tests/concurrency/test_submit_races.py`

**Implements:** DESIGN §4.2 (approve), §4.3 (reject), §4.5 (deadlock argument and race table), §8.3 (concurrency plan). Rules R14, R15, R16, R17, R18, and R9, R10, R13 under concurrency. Decisions Q4, Q5.

**Tests that must pass**
- MUST: P1, P2, P3, P4, P6, P7, P8, P9, B1, then X1, X2, X3, X4, X5, X6, plus the invariant check after every X run
- SHOULD: P5, X7

**Watch out for**
- In approve and reject: lock the request row, then the balance row, then check self (403), then status (409). The self check comes **before** the status check (R15, P5).
- Reject also locks the balance row (Q4). A blank comment after `strip()` returns 422, but only once status is PENDING (Q5).
- `23514` maps to 409 `INSUFFICIENT_BALANCE`.
- Harness: one `SessionLocal()` per thread, calling service functions directly behind a `threading.Barrier` (give it a timeout so a bug fails rather than hangs). An `AppError` counts as its HTTP status. **Any other exception counts as a 500, and the test fails.** Repeat each scenario 20× with `parametrize`.

**Verify**
```bash
cd backend
pytest -q -m "not concurrency"
for i in 1 2 3; do pytest -m concurrency -q || break; done   # 3 clean runs = not flaky
```

**Explain-back:** the lock order in approve and why it cannot deadlock against submit (§4.5); why self is checked before status; how the barrier harness turns a race into a repeatable test; what the invariant checker asserts.

**Commit:** `feat(approval): approve/reject with row locks and concurrency race tests`

### Step 3.2: Manager endpoints

**Goal:** `GET /manager/requests` serves the pending queue (oldest first, with `employee_available`) and history (status filter). Neither ever includes the caller's own requests. **Backend freeze** after this step.

**Files touched**
- `backend/app/services/approval_service.py` (`list_manager_requests`)
- `backend/app/schemas/leave_request.py` (`ManagerRequestOut` with `employee_available`)
- `backend/app/routers/manager.py`, `app/main.py` (router; confirm `CORS_ORIGINS`)
- `backend/app/cli.py` (`ensure-balances`; see the cut list)
- `backend/tests/api/test_manager_views.py`

**Implements:** DESIGN §5 row `/manager/requests`, the data needs of §7 `/manager/queue` and `/manager/history`, R19, R2 (CLI path). Decisions Q6, Q7, Q8.

**Tests that must pass**
- MUST: V1, plus a full re-run of every MUST test so far
- SHOULD: V2, V4 (complete), then any SHOULD left over from Phases 1–3

**Verify**
```bash
cd backend
pytest -q                                                       # entire backend suite green = freeze gate
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"manager1@example.com","password":"Manager@123"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $TOKEN" 'localhost:8000/manager/requests?status=PENDING'
```

**Explain-back:** how the caller's own requests are excluded; how `employee_available` is computed per row; why PENDING sorts ascending and history descending.

**Commit:** `feat(manager): pending queue and history endpoint with employee_available`

### Exit gate: Phase 3 (backend freeze)

- [ ] `pytest -q` green: the entire backend suite.
- [ ] `pytest -m concurrency -q` green three runs in a row, X1–X6 with invariant checks.
- [ ] curl, local:
  - employee1 submits; manager1 approves → `APPROVED`, employee1's `used` goes up on `/balances`.
  - manager1 submits; manager1 approves their own request → 403 `SELF_ACTION_FORBIDDEN`; manager2 approves it → 200.
  - manager1 rejects a PENDING request with no comment → 422 `COMMENT_REQUIRED`.
  - `GET /manager/requests?status=PENDING` as manager1 → oldest first, none of manager1's own, `employee_available` set.
  - employee1 calls `/manager/requests` → 403 `FORBIDDEN`.
- [ ] Two commits pushed; explain-back bullets for 3.1–3.2 in `NOTES.md`.
- [ ] Tag the freeze: `git tag backend-freeze && git push --tags`.

---

## Phase 4: Employee UI

### Step 4.1: React warm-up

**Goal:** A throwaway, low-stakes first contact with React before touching the real frontend: a fresh Vite app with one page that logs in with a hard-coded user and shows the result of `GET /me`. This is practice, not product code; it lives **outside** the repo.

- `npm create vite@latest react-warmup -- --template react` in a scratch directory outside the repo.
- One component: a button that calls `POST /auth/login` for employee1, stores the token in `useState`, then fetches `/me` in a `useEffect` and renders the name, email and role. Render an error message if either call fails.
- Run it against the local backend. Its default `CORS_ORIGINS` (`http://localhost:5173`) already allows the Vite dev server.

**React primer (learn only this)**
- Components and props; `useState`; `useEffect` with `[]` to load data on mount; one Context for auth.
- react-router v6: `BrowserRouter`, `Routes`/`Route`, `Navigate`, `useNavigate`, `useParams`, `Link`.
- Controlled form inputs: `value` plus `onChange`.
- Every page follows one pattern: state for `data`, `error` and `loading`; one effect that calls an `endpoints.js` function; render the error with `ErrorBanner`.
- Skip: TypeScript, Redux/Zustand, React Query, form libraries, UI kits, CSS-in-JS.

**Verify**
```bash
cd react-warmup && npm install && npm run dev   # page at http://localhost:5173 shows employee1's name and role
```

**Explain-back:** when the effect runs and why it needs a dependency list; what triggers a re-render; where the token lives; what the browser does with CORS here.

**Commit:** none in the repo (the warm-up is throwaway). Commit the `NOTES.md` bullets with step 4.2.

### Step 4.2: React shell + login

**Goal:** A Vite React app (plain JS) with routing, the API client (including the 401 rule), AuthContext with route guards, and working login and signup pages. After login, users land on role-specific placeholder pages. While login waits for the server, the page shows "Signing in..."; if the wait passes 5 s, it also shows "The server may be waking up, please wait" (free-tier cold starts).

**Files touched**
- `frontend/` (Vite scaffold: `package.json`, `vite.config.js`, `index.html`), `frontend/.env.example`
- `frontend/src/main.jsx`, `src/App.jsx`, `src/index.css` (one plain stylesheet)
- `frontend/src/api/client.js`, `src/api/endpoints.js` (auth and `/me` only for now)
- `frontend/src/auth/AuthContext.jsx` (`RequireAuth`, `RequireManager`)
- `frontend/src/pages/LoginPage.jsx`, `pages/SignupPage.jsx`
- `frontend/src/components/NavBar.jsx`, `components/ErrorBanner.jsx`

**Implements:** DESIGN §1.2 (frontend layout), §1.3 (FE rows: pages, components, api client, AuthContext), §6.1 step 5, §7 rows `/login`, `/signup`, `/`, and the nav and 401 rule paragraphs. UI side of R21 and R22, with error codes from Q1 and Q2.

**Tests that must pass**
- DESIGN §8 defines no frontend automated tests. Do not add a test framework now.
- MUST: the backend suite stays green, and `npm run build` succeeds.
- Manual checklist:
  1. A wrong password shows `INVALID_CREDENTIALS` inline and the page does not reload.
  2. Signup with a wrong code shows the `SIGNUP_FAILED` message inline.
  3. employee1 lands on `/dashboard`; manager1 lands on `/manager/queue`.
  4. A browser refresh keeps you logged in (AuthContext calls `/me` on boot).
  5. Removing the token in devtools and navigating redirects to `/login`.
  6. Slow login: suspend the backend with Ctrl+Z in its terminal, then log in. "Signing in..." appears at once; after 5 s, "The server may be waking up, please wait" appears as well. Resume with `fg`; login completes and both messages disappear.

**Verify**
```bash
cd frontend && npm install && npm run build && npm run dev   # then run the manual checklist at http://localhost:5173
```

**Explain-back:** how `client.js` handles a 401 and why login/signup are the exception; how `RequireAuth` and `RequireManager` decide; what AuthContext does on boot.

**Commit:** `feat(web): React shell with router, API client, auth context, login and signup`

### Step 4.3: Employee screens

**Goal:** An employee can complete their full flow in the browser: see balances, submit with a live working-day count and inline server errors, list their requests with badges and decision comments, cancel PENDING requests, and open a request's detail.

**Files touched**
- `frontend/src/pages/DashboardPage.jsx`, `NewRequestPage.jsx`, `MyRequestsPage.jsx`, `RequestDetailPage.jsx`
- `frontend/src/components/BalanceCards.jsx`, `LeaveRequestForm.jsx`, `RequestsTable.jsx`, `StatusBadge.jsx`
- `frontend/src/utils/workingDays.js`
- `frontend/src/api/endpoints.js` (balances and leave-requests), `src/App.jsx` (routes), `components/NavBar.jsx`

**Implements:** DESIGN §7 rows `/dashboard`, `/requests/new`, `/requests`, `/requests/:id`, and §1.3 (components render from props, pages fetch). UI side of R3 (cards), R4 (preview only; the server is authoritative), R5–R10 (date codes shown on the date fields, others in the banner), R13 (Cancel only on PENDING) and R20.

**Tests that must pass**
- MUST: the backend suite stays green, and `npm run build` succeeds.
- Manual checklist (as employee1, dates in Nov 2026):
  1. Mon–Fri previews 5 days, and submitting succeeds.
  2. Sat–Sun shows `NO_WORKING_DAYS` on the date field.
  3. Re-submitting the same dates shows `OVERLAPPING_REQUEST` in the banner.
  4. Dashboard Pending and Available update after the submit.
  5. Cancel sets the status to Cancelled and restores Available. No Cancel button appears on non-PENDING rows.
  6. Opening another user's request id in the URL shows a 403 message.

**Verify**
```bash
cd frontend && npm run build && npm run dev   # backend running; run the checklist above
```

**Explain-back:** how the form maps a server error code to a field or the banner; why the client-side day count is only a preview; how the list refreshes after cancel.

**Commit:** `feat(web): employee dashboard, new request form, my requests and detail`

### Step 4.4: Frontend deploy

**Goal:** The static site is live, and login works against the live API. From this step on, the backend start command runs the migration **and** the seed, so the demo accounts exist on the hosted database. This changes host config and env vars only, not backend code, so the freeze holds.

**Files touched**
- Host config (for example `render.yaml`): add the static site; add the seed to the backend start command
- `frontend/public/_redirects` or the host's rewrite rule (SPA fallback from `/*` to `/index.html`)
- `frontend/.env.example` (production note for `VITE_API_BASE_URL`)

**Implements:** DESIGN §6.3 (seed), §6.4 (environment variables: `CORS_ORIGINS`, `VITE_API_BASE_URL`), §7 (client-side routes, which need the SPA fallback).

- Backend start, from now on: `alembic upgrade head && python -m scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Both are idempotent, so running them on every start is safe.
- Backend env: `CORS_ORIGINS` set to the static site's exact origin (scheme and host, no trailing slash).
- Static site: build `npm install && npm run build`, publish `dist`, with `VITE_API_BASE_URL` set to the backend URL. Vite bakes it in at build time, so rebuild if it changes.

**Tests that must pass**
- MUST: the backend suite stays green, and `npm run build` succeeds.
- Live checks:
  1. `VITE_API_BASE_URL`: logging in on `https://<web-host>` sends requests to `https://<api-host>` (devtools Network tab), not to `localhost`.
  2. `CORS_ORIGINS`: no CORS errors in the console, and the preflight below echoes the web origin.
  3. SPA rewrite: opening `https://<web-host>/dashboard` directly loads the app (redirecting to `/login` when logged out) instead of a 404.
  4. employee1 logs in and lands on `/dashboard`; manager1 logs in and lands on `/manager/queue`.
  5. The deploy log shows the migration and the seed running before `uvicorn`.

**Verify**
```bash
curl -fsS https://<api-host>/health                                          # {"status":"ok"}
curl -sS -i -X OPTIONS https://<api-host>/auth/login \
  -H 'Origin: https://<web-host>' -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' | grep -i access-control-allow-origin   # https://<web-host>
curl -fsS -o /dev/null -w '%{http_code}\n' https://<web-host>/dashboard      # 200 (SPA rewrite)
# Browser: run the live checks above
```

**Explain-back:** why `VITE_API_BASE_URL` needs a rebuild when it changes; what the SPA rewrite fixes; why `CORS_ORIGINS` must match the web origin exactly; why the seed now runs in the start command and why that is safe.

**Commit:** `chore(deploy): deploy static frontend with SPA rewrite and seeded hosted DB`

### Exit gate: Phase 4

- [ ] `pytest -q` still green; `npm run build` succeeds.
- [ ] Browser: all six checks from step 4.2 pass.
- [ ] Browser: all six checks from step 4.3 pass.
- [ ] Static site deployed; login works against the live API (`VITE_API_BASE_URL`, SPA rewrite, `CORS_ORIGINS` verified).
- [ ] Three commits pushed (4.2, 4.3, 4.4); explain-back bullets for 4.1–4.4 in `NOTES.md`.

If the end of Monday 19 Oct arrives and this gate is not green, apply the cut list now (see **Cut list**).

---

## Phase 5: Manager UI

### Step 5.1: Manager screens + acceptance flow

**Goal:** Managers get a "My leave" page, a pending queue with Approve (optional comment) and Reject (comment required), and history with a status filter. The SPEC §12 acceptance flow works end to end in the browser.

**Files touched**
- `frontend/src/pages/MyLeavePage.jsx`, `ManagerQueuePage.jsx`, `ManagerHistoryPage.jsx`
- `frontend/src/components/DecisionDialog.jsx`
- `frontend/src/pages/RequestDetailPage.jsx` (approve and reject for managers who are not the owner; see the cut list)
- `frontend/src/api/endpoints.js`, `src/App.jsx`, `components/NavBar.jsx` (manager links: My leave, Queue, History)

**Implements:** DESIGN §7 rows `/my-leave`, `/manager/queue`, `/manager/history`, and the `/requests/:id` approve/reject condition. UI side of R14–R19. Decisions Q6 (label the column "Available (after pending)"), Q7, Q8.

**Tests that must pass**
- MUST: the backend suite stays green, and `npm run build` succeeds.
- Manual acceptance (SPEC §12), with two browser profiles (or one normal and one private window):
  1. employee1 submits; manager1 approves it; employee1's Used goes up.
  2. employee1 submits; manager1 rejects it without a comment (blocked; 422 shown); with a comment, the comment appears in employee1's list.
  3. employee1 submits, then cancels; the request disappears from the queue.
  4. manager1 submits on My leave; it is absent from manager1's queue; manager2 approves it.
  5. **Concurrent decision (stale-queue method).** Two clicks are never truly simultaneous by hand, so make one queue stale on purpose:
     1. employee1 submits a request.
     2. Open `/manager/queue` as manager1 in one profile and as manager2 in the other. Both show the request.
     3. manager2 approves it. manager2's row disappears.
     4. **Without refreshing**, manager1 clicks Approve (or Reject with a comment) on the same, now stale, row.
     5. Expected: manager1 sees the `ALREADY_ACTIONED` (409) message, the queue refetches, and the row is gone. employee1's Used went up exactly once.

**Verify**
```bash
cd frontend && npm run build && npm run dev   # run the acceptance flow above
```

**Explain-back:** how the queue handles a 409 (message plus refetch); why reject's comment check also lives on the server; how My leave reuses the employee components.

**Commit:** `feat(web): manager queue, history, my-leave and approve/reject dialog`

### Exit gate: Phase 5

- [ ] `pytest -q` still green; `npm run build` succeeds.
- [ ] Browser: acceptance steps 1–5 above pass locally, including the stale-queue 409.
- [ ] Manager history filters by status and never shows the manager's own requests.
- [ ] Commit pushed; explain-back bullets for 5.1 in `NOTES.md`.

---

## Phase 6: Ship

### Step 6.1: Full redeploy

**Goal:** The full app, including the manager UI, is live over HTTPS on the host proven in Phase 1. The hosted database is migrated and seeded, and the acceptance flow works on the live URL. DESIGN leaves deployment open, so the choices below belong to this plan. The backend skeleton (step 1.3) and the static site (step 4.4) are already deployed, so this is a redeploy plus a re-check.

**Files touched**
- Host config (for example `render.yaml`): backend web service, static site, database (all set up by step 4.4; re-check)
- `backend/app/core/config.py` (accept the host's `postgres://` URL and rewrite it to `postgresql+psycopg://`; added in step 1.3, re-check)
- `frontend/public/_redirects` or the host's rewrite rule (SPA fallback from `/*` to `/index.html`; added in step 4.4, re-check)
- `backend/.env.example`, `frontend/.env.example` (production notes)

**Implements:** DESIGN §6.4 (environment variables), §9.2 (`btree_gist` risk, already de-risked in Phase 0 and proven in step 1.3), SPEC §13 assumption 10 (HTTPS handled by the host).

- Backend build: `pip install -r requirements.txt` (Python pinned to 3.12 since step 1.3).
- Backend start: `alembic upgrade head && python -m scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT` (in place since step 4.4).
- Environment: `SECRET_KEY` (random, not the dev one), `SIGNUP_CODE`, `CORS_ORIGINS` set to the frontend URL, and `DATABASE_URL`.
- Frontend: build with `VITE_API_BASE_URL` set to the backend URL. Vite bakes it in at build time, so rebuild if it changes.

**Free-tier notes**
- **No `preDeployCommand`.** Free web services usually cannot run a pre-deploy step, so the migration and seed run in the start command, before `uvicorn`. Both are idempotent, so running them on every start is safe.
- **Cold starts.** A free backend spins down when idle, and the first request after that can take tens of seconds. The static frontend does not sleep, so the first login can look like it hangs. Warm the backend with `curl https://<api-host>/health` a few minutes before any demo or review, and say so in the README and the submission email.
- **Database expiry.** Free managed databases can expire after a fixed period. Write the expiry date shown in the host dashboard into `NOTES.md` and the README, and check that it falls after the review window.

**Tests that must pass**
- MUST: the full `pytest -q` suite passes locally before the redeploy (gate).
- Live smoke checks below, plus acceptance steps 1, 4 and 5 from step 5.1 on the live URL.

**Verify**
```bash
curl -fsS https://<api-host>/health                      # {"status":"ok"}
curl -fsS -X POST https://<api-host>/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"employee1@example.com","password":"Employee@123"}'
# Browser: open https://<web-host>/requests directly (SPA rewrite works), log in, run the acceptance steps
```

**Explain-back:** what each service runs at build and start; why the frontend needs a rebuild when the API URL changes; what the SPA rewrite fixes; how CORS is set for production.

**Commit:** `chore(deploy): redeploy full app and re-check production config`

### Step 6.2: README + fresh-clone check

**Goal:** The README has every section SPEC §16 requires, and a fresh clone can be set up from it alone.

**Files touched**
- `README.md`: **setup**, **stack**, **architecture**, **data model**, **assumptions**, **limitations** (SPEC §16), plus the live URL, demo accounts, the join-code note, the cold-start note, the DB expiry date, and how to run tests, including `-m concurrency`
- `CLAUDE.md`: final commands and architecture summary
- `backend/.env.example`, `frontend/.env.example` (final review)

**Implements:** SPEC §16. Content comes from DESIGN §1.1 (architecture), §2.2 (ER diagram), §4.5 (why concurrency is safe, in two sentences), §10 (decisions, as assumptions), and SPEC §13, §14, §15. Add any cuts you made to the limitations.

**Tests that must pass**
- MUST: a final full `pytest -q` run and `npm run build`.
- Fresh-clone check: clone into a new directory, follow the README word for word, and reach the login page.

**Verify**
```bash
cd backend && pytest -q && cd ../frontend && npm run build
git clone <repo-url> ../lm-fresh   # follow README from scratch
```

**Explain-back:** which README instructions the fresh clone exposed as wrong or missing, and what you changed.

**Commit:** `docs: README with setup, architecture, data model, assumptions and limitations`

### Step 6.3: Submission

**Goal:** The client can open the repo, reach the live app, and log in as each role without asking you anything.

- **Repo access.** Make the repository public, or add the client's GitHub account as a collaborator, then confirm from a logged-out or other-account browser that the link opens.
- **No secrets committed.** Only `.env.example` files are tracked, now and in history:
  ```bash
  git ls-files | grep -E '(^|/)\.env$'                               # must print nothing
  git log --all --name-only --format= | grep -E '(^|/)\.env$' | sort -u   # must print nothing
  ```
  If either prints a file, remove it, rotate every secret it contained (`SECRET_KEY`, `SIGNUP_CODE`, DB password), and redeploy.
- **Warm the backend** with `curl https://<api-host>/health` just before sending.
- **Email the client** with:
  - the repo link;
  - the live URL (frontend) and the API `/health` URL;
  - demo logins: `manager1@example.com` / `manager2@example.com` (`Manager@123`) and `employee1–3@example.com` (`Employee@123`);
  - the `SIGNUP_CODE` for the hosted app, so they can try signup;
  - one line on cold starts ("the first request can take up to a minute") and the database expiry date.

**Explain-back:** what the client receives and how each piece was checked.

**Commit:** none required beyond a final push; confirm `git status` is clean and `main` is pushed.

### Step 6.4: Demo script and recording

**Goal:** The demo is scripted and rehearsed, with a recorded fallback.

- Write a 5-minute script: employee submits, gets the inline error, and cancels; manager1 approves; manager2 approves manager1's own leave; rejecting without a comment is blocked; the stale-queue 409; then show `pytest -m concurrency` passing.
- Use future weekdays in Nov–Dec 2026, so live data from testing does not collide. Check the live data before the demo.
- Warm the backend before starting.
- Rehearse twice. Record a 3-minute screen capture of the live app as a fallback in case the live demo breaks.

**Explain-back:** the demo order and the one-sentence reason behind each beat.

**Commit:** none required (keep the script in `NOTES.md` if you want it versioned).

### Exit gate: Phase 6

- [ ] `pytest -q` green and `npm run build` succeeds on the final commit.
- [ ] Live: `/health` ok; acceptance steps 1, 4 and 5 pass on the live URL; deep link to `/requests` loads.
- [ ] Fresh clone reaches the login page by following the README alone.
- [ ] No `.env` tracked or in history; repo opens for the client.
- [ ] Submission email sent with repo link, live URL, demo logins and `SIGNUP_CODE`.
- [ ] Demo rehearsed twice; recording saved.
- [ ] Final commit pushed.

---

## Cut list

Cuts are triggered by **progress, not by the clock**. Apply them **in order**, one at a time, when either:

- a phase's exit gate is still red after the work in that phase is done, and the next phase is blocked by it; or
- the end of Monday 19 Oct arrives and the Phase 4 gate is not green.

After each cut, re-check the gate before taking the next one. Every cut you make goes in the README limitations.

| # | Cut | Why it is safe |
|---|---|---|
| 1 | `app/cli.py ensure-balances` | SPEC §3 says rows are created lazily **or** by the CLI; lazy creation already covers it (R2) |
| 2 | `/health` 503 `DB_UNAVAILABLE` path, replaced by a plain 200 | Marked *(proposed)* in DESIGN; not in SPEC |
| 3 | Status filter on the employee "My requests" page | SPEC requires the filter only on manager history; the API still supports it |
| 4 | Approve/Reject buttons on the request detail page | DESIGN-only; the queue already has them, as SPEC §10 requires |
| 5 | Unwritten SHOULD tests (U10–U12, A4, A6, H1, P5, V2–V5, X7) | DESIGN §8 classes them as non-brief; MUST already covers the brief |
| 6 | `DecisionDialog` modal, replaced by an inline comment box and two buttons per queue row | Same API calls and rules; it only looks different |
| 7 | "My leave" as a custom layout, replaced by the three existing components stacked with no new layout | SPEC needs the page, not a design |
| 8 | Styling beyond one plain stylesheet; responsive layout | SPEC §14: responsive is best-effort |

**Never cut:** any MUST test (especially D1–D3 and X1–X6), the exclusion constraint and the CHECKs, server-side role and self-action checks, the `{code, message}` error shape, signup with the join code, the live working-day count, the six README sections, the acceptance flow, and **the live deployment**.

### If the host fails

1. **Switch host or database provider.** The deploy skeleton in step 1.3 is small on purpose, so moving it is cheap: create the database elsewhere, re-run the `btree_gist` check from step 0.2, point `DATABASE_URL` at it, and redeploy. A managed database from one provider can back a web service on another.
2. **If it still fails, contact the client** with what failed, what you tried, and a proposed alternative. Do not silently fall back to a local-only demo.

---

## Live-change drills

Small changes a reviewer might ask for live. Practise each on a throwaway branch once Phase 5's gate is green (`git switch -c drill-N`, make the change, run the named tests, then `git switch main && git branch -D drill-N`). For each one, know where it lives before you open an editor.

| # | Change | Where it lives | Tests to update or run | Gotcha |
|---|---|---|---|---|
| 1 | Earned entitlement goes from 12 to 15 days | `backend/app/core/constants.py` (`ENTITLEMENTS`); the only writer is `balance_service.ensure_balance_rows` | A1, B2, E1 assert 12 | Existing `leave_balances` rows keep 12; say whether you would backfill them with a data migration. The frontend needs no change, because cards read `entitlement` from `/balances` |
| 2 | Treat a fixed list of public holidays as non-working days | `backend/app/services/working_days.py` (`count_working_days`), holiday list in `core/constants.py`; mirror it in `frontend/src/utils/workingDays.js` | U1–U4 still pass; add one test with a holiday inside the range | The client preview and the server must agree, or the form shows a different count from the saved one. A range of only holidays must give `NO_WORKING_DAYS` |
| 3 | Make `reason` required and cap it at 200 characters | `backend/app/schemas/leave_request.py` (`LeaveRequestIn`); `frontend/src/components/LeaveRequestForm.jsx` (`required`, `maxLength`) | S-tests that submit without a reason; add one for a missing reason → 422 | The DB column stays `VARCHAR(500)` and nullable, so no migration is needed; existing rows with no reason must still render |
| 4 | Show "Decided by" and the decision date in manager history | `frontend/src/pages/ManagerHistoryPage.jsx` and `components/RequestsTable.jsx` (an optional column) | None on the backend; `npm run build` and a browser check | `decided_by_name` and `decided_at` are already in `LeaveRequestOut`, so this is frontend-only. Cancelled rows have no decider, so show a dash |
| 5 | Shorten the session from 60 to 30 minutes | `backend/app/core/constants.py` (`JWT_EXPIRE_MINUTES`); `expires_in` in `schemas/auth.py` if it is hard-coded there | U12 asserts `exp − iat = 3600`; the signup/login response asserts `expires_in: 3600` | There are no refresh tokens, so users are sent to `/login` sooner. The frontend's 401 rule already handles it |
