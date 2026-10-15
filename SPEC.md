# Leave Management MVP: Specification

**Deadline:** 20 Oct 2026, 5 PM
**Stack:** React + Vite (plain JS) · FastAPI · PostgreSQL

## 1. Goals

A small company needs a simple way for employees to request leave and for managers to approve or reject it, with balances that are always correct and never negative.

## 2. Roles

| Role | Capabilities |
|---|---|
| Employee | Sign up, log in, view own balances, submit leave, view own requests, cancel own Pending requests |
| Manager | Everything an Employee can do (managers have their own balances and requests), plus: view the pending queue, approve/reject any other user's request, view all-requests history, view team calendar |

- There is more than one manager.
- **Any manager** can act on any request, except their own. First action wins.
- A manager can never see an actionable entry for, or act on, their own request (403 server-side).

## 3. Leave types and balances

| Type | Entitlement per calendar year |
|---|---|
| Earned | 12 days |
| Sick | 10 days |

- Tracked separately; no conversion between types.
- Leave year = calendar year (1 Jan to 31 Dec), in the company timezone.
- Full grant on account creation for the current year, no proration, no carry-forward.
- At the start of a new year, balance rows for that year are created lazily on first access (or by the seed/CLI command), so every user has 12 Earned + 10 Sick for it.

### Balance definitions (per user, type, year)

- `entitlement`: 12 or 10
- `used` = sum of `days` of **Approved** requests
- `pending` = sum of `days` of **Pending** requests
- `available` = `entitlement − used − pending`

**Balance reduces only on approval** (`used` changes only when a request becomes Approved). Pending days are *reserved*: they reduce `available` so that a user cannot submit more than they could ever be granted, but they do not reduce `used`.

Invariant: `used ≤ entitlement` always, and `available ≥ 0` always.

## 4. Request model and statuses

Fields: `id`, `user_id`, `leave_type` (EARNED | SICK), `start_date`, `end_date` (inclusive, calendar dates), `days` (computed, stored), `reason` (optional), `status`, `decided_by`, `decided_at`, `decision_comment`, `created_at`.

### Statuses and transitions

```
Pending ──approve──▶ Approved   (terminal)
Pending ──reject───▶ Rejected   (terminal)
Pending ──cancel───▶ Cancelled  (terminal)
```

- **Only Pending** requests can be cancelled, and only by the requester.
- Approved, Rejected and Cancelled are terminal. Approved leave cannot be cancelled or revoked in the MVP.
- Pending requests stay actionable regardless of dates (a manager can approve or reject after the start date has passed).
- No auto-expiry.

## 5. Working-day calculation

- Working days are **Mon to Fri**. Saturday and Sunday are excluded.
- **Public holidays are ignored** (they count as working days).
- Leave is counted in **full days only**; no half-days.
- `days` = number of Mon-Fri dates in `[start_date, end_date]` inclusive.
- A range with **zero working days** (e.g. Sat to Sun) is rejected with a validation error.

## 6. Submission rules

A submit is rejected, with the error code below, when:

| Rule | HTTP |
|---|---|
| `end_date < start_date` | 422 |
| Range contains zero working days | 422 |
| Range spans more than one calendar year (must be split into two requests) | 422 |
| Dates are not in the **current calendar year** (company timezone) | 422 |
| Range overlaps any of the user's own **Pending or Approved** requests (any leave type) | 409 |
| `days > available` for that type and year | 409 |

- Backdating within the current year is allowed for both types.
- Rejected and Cancelled requests never block a new request.
- Overlap check is by date range regardless of leave type, to prevent the same day being deducted twice.

## 7. Approval rules

Performed in **one database transaction**:

1. Lock the request row (`SELECT … FOR UPDATE`) and the user's balance row for that type/year.
2. Verify status is still `Pending`, else **409** ("already actioned").
3. Verify approver ≠ requester, else **403**.
4. On approve: re-verify `used + days ≤ entitlement` (and no overlap with another Approved request), else **409**; set `Approved`, `decided_by`, `decided_at`, optional comment.
5. On reject: **reason is required** (422 if empty); set `Rejected` and store the reason.

Two managers acting simultaneously: the second gets 409. Approving two requests that together exceed the balance: the second fails with 409 (insufficient balance), leaving it Pending so the manager can reject it.

A database-level guard (CHECK/trigger or constrained update on the balance row) backs up the application check so `used` can never exceed `entitlement`.

## 8. Authentication and user management

- Email + password; bcrypt (or argon2) hashed; JWT bearer tokens with expiry.
- **Signup (employees only):** public page requiring a company **join code** compared to the `SIGNUP_CODE` environment variable (documented in `.env.example` and README, never hard-coded). Wrong or missing code returns a generic error.
  - Role is set server-side to EMPLOYEE; the client can never supply it.
  - Server generates a unique `employee_code` (`EMP-0001` style).
  - Server creates 12 Earned + 10 Sick balance rows for the current calendar year.
- **Managers:** created only by an **idempotent seed script** (safe to run twice), never via signup or UI.
  - Seed at least 2 managers (so a manager's leave has someone else to approve it) and 3-4 demo employees.
  - Seeded users have known demo passwords and the same balance rows as signed-up users.
- No admin UI, no role promotion, no password reset in the MVP.

## 9. API (indicative)

| Method & path | Who | Purpose |
|---|---|---|
| `POST /auth/signup` | public | Employee signup with join code |
| `POST /auth/login` | public | Returns JWT |
| `GET /me` | any | Profile and role |
| `GET /balances` | any | Own balances for current year (entitlement, used, pending, available) |
| `POST /leave-requests` | any | Submit |
| `GET /leave-requests` | any | Own requests (filter by status) |
| `POST /leave-requests/{id}/cancel` | requester | Cancel Pending |
| `GET /manager/requests?status=` | manager | Pending queue and history (excludes own requests from actionable queue) |
| `POST /leave-requests/{id}/approve` | manager | Approve (optional comment) |
| `POST /leave-requests/{id}/reject` | manager | Reject (reason required) |
| `GET /manager/calendar?month=YYYY-MM` | manager | Approved leave by day, all employees |
| `GET /manager/balances` | manager | All employees' balances (optional, supports queue context) |

Errors use a consistent JSON shape `{ "code": "...", "message": "..." }` with 403 role violations, 409 conflicts (overlap, insufficient balance, already actioned), 422 validation.

Role checks and the "not your own request" check are enforced **server-side**, not only in the UI.

## 10. Frontend (React + Vite, plain JS)

**Employee**
- Login, signup (with join code)
- Dashboard: Earned and Sick balances (entitlement / used / pending / available)
- New request form with live working-day count and inline server errors
- My requests list with status badges, manager comment/rejection reason, and a Cancel button on Pending only

**Manager** (in addition to the employee screens)
- Pending queue, oldest first: employee, type, dates, days, employee's remaining balance, Approve / Reject (reason modal)
- All-requests history with filters (status, employee, type)
- Team calendar: month view of Approved leave across employees
- Own requests appear only in "My requests", never in the actionable queue

## 11. Data model (PostgreSQL)

- `users`: id, employee_code (unique), name, email (unique), password_hash, role (`EMPLOYEE`|`MANAGER`), created_at
- `leave_balances`: user_id, leave_type, year, entitlement; unique (user_id, leave_type, year). `used`/`pending` derived from requests (or maintained under lock with a CHECK).
- `leave_requests`: fields in section 4; CHECK `end_date >= start_date`, CHECK `days > 0`, indexes on (user_id, status), (status), (start_date, end_date)
- Overlap protection: application check inside the submit transaction plus a DB exclusion constraint on `(user_id, daterange)` for Pending/Approved rows where feasible.
- Migrations via Alembic (or equivalent).

## 12. Testing and acceptance

Backend tests must cover:
- Working-day count: weekdays only, weekend-only rejected, single day, range across weekends
- Insufficient balance at submit (including pending reservation) and at approval
- Overlap with Pending and Approved blocked; Rejected/Cancelled not blocking; cross-type overlap blocked
- Year-boundary and out-of-year rejection
- Cancel allowed only for Pending and only by owner
- Approve/reject by non-manager (403), by requester-manager (403), on already-actioned request (409), reject without reason (422)
- Concurrent approvals never drive `used` above entitlement
- Signup: wrong/missing code rejected, role cannot be injected, balances and employee_code created
- Seed script idempotent

Acceptance: a seeded manager and employee can complete submit, approve, reject and cancel flows end-to-end in the browser against PostgreSQL.

## 13. Assumptions

1. Single company, single timezone, configured by an env var (e.g. `COMPANY_TZ`); "today" and "current year" are derived in it.
2. Dates are plain calendar dates with no time component.
3. Pending days are reserved against `available` at submit time; `used` only changes on approval.
4. Any manager can act on any request; no reporting lines.
5. Managers have their own balances and can submit leave, approved by a different manager.
6. Past dates within the current year are allowed for both leave types; trust is placed in the manager approval step.
7. Year rollover creates the new year's balances (lazily or via command); nothing carries forward.
8. Weekend is Sat/Sun for everyone; no per-employee work patterns.
9. Join code is shared by all employees and supplied out of band by the company.
10. A single deployment with HTTPS terminated by the host; JWTs are short-lived, with no refresh tokens.
11. Demo passwords in the seed script are for non-production use only.
12. No email notifications; users check the app for status.

## 14. Out of scope

- Public-holiday calendar or regional holiday handling
- Half-days, hourly leave, and other leave types (casual, maternity, unpaid, comp-off)
- Carry-forward, encashment, proration for mid-year joiners, accrual
- Revoking or cancelling Approved leave; editing a submitted request (cancel and resubmit instead)
- Reporting lines, delegation, escalation, multi-level approval
- Admin UI, role promotion, user deactivation, manager reassignment
- Password reset, email verification, SSO, MFA, verified invitation links
- Email/Slack notifications, audit-log UI, exports/reports, attachments (e.g. medical certificates)
- Per-employee work schedules, multiple timezones, localisation
- Mobile apps; responsive web is best-effort

## 15. Known limitations (to improve next)

- Shared join code (not per-person); no email verification
- No admin UI or role promotion; managers only via seed
- Approved leave cannot be undone without a manual DB fix
- Pending requests are not auto-expired and may sit indefinitely
