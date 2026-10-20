# Leave Management MVP: Specification

**Deadline:** 20 Oct 2026, 5 PM
**Stack:** React + Vite (plain JS) · FastAPI · PostgreSQL

## 1. Goals

A small company needs a simple way for employees to request leave and for managers to approve or reject it, with balances that are always correct and never negative.

## 2. Roles

| Role | Capabilities |
|---|---|
| Employee | Sign up, log in, view own balances, submit leave, view own requests, cancel own Pending requests |
| Manager | Everything an Employee can do (managers have their own balances and requests), plus: view the pending queue, approve/reject any other user's request, view all-requests history |

- There is more than one manager.
- Every user has an optional manager (`users.manager_id`). A MANAGER whose manager is empty is the **super manager**; there is no separate role.
- **Employee requests:** any manager can act on them, except the requester's own. First action wins.
- **Manager requests:** only the requester's own manager can approve or reject them. Any other manager gets 403 `NOT_REQUESTERS_MANAGER`. The check runs after the self-action check (403 `SELF_ACTION_FORBIDDEN`) and before the already-actioned check (409).
- A manager can never see an actionable entry for, or act on, their own request (403 server-side), and the pending queue and history do not list manager requests the viewer cannot act on.
- The super manager has no manager to approve their leave, so they cannot submit leave (403 `MANAGER_HAS_NO_MANAGER`). They can still decide requests and see their balances.
- A new signup gets a manager at random from the managers who have a manager (never the super manager); if there are none the employee has no manager. The assignment is informational for employee requests: it gives them no priority.

## 3. Leave types and balances

| Type | Entitlement per calendar year |
|---|---|
| Earned | 12 days |
| Sick | 10 days |

- Tracked separately; no conversion between types.
- Leave year = calendar year (1 Jan to 31 Dec), in the company timezone.
- Full grant on account creation for the current year, no proration, no carry-forward.
- At the start of a new year, balance rows for that year are created lazily on first access (or by the seed/CLI command), so every user has 12 Earned + 10 Sick for it. `GET /balances` creates any missing current-year rows.
- The 12/10 entitlements come from **one constant**, used everywhere balance rows are created.

### Balance definitions (per user, type, year)

- `entitlement`: 12 or 10, stored in `leave_balances.total_days`
- `used`: stored in `leave_balances.used_days`; changes only when a request is **Approved** (incremented by its `days`)
- `pending` = `SUM(days)` of the user's **Pending** requests for that type and year, computed at query time (not stored)
- `available` = `entitlement − used − pending`

**Balance reduces only on approval** (`used` changes only when a request becomes Approved). Pending days are *reserved*: they reduce `available` so that a user cannot submit more than they could ever be granted, but they do not reduce `used`.

Invariant: `used ≤ entitlement` always, and `available ≥ 0` always.

## 4. Request model and statuses

Fields: `id`, `user_id`, `leave_type` (limited to EARNED or SICK), `start_date`, `end_date` (inclusive, calendar dates), `days` (computed, stored), `reason` (optional, max 500 characters), `status`, `decided_by`, `decided_at`, `decision_comment`, `created_at`.

### Statuses and transitions

```
Pending ──approve──▶ Approved   (terminal)
Pending ──reject───▶ Rejected   (terminal)
Pending ──cancel───▶ Cancelled  (terminal)
```

- **Only Pending** requests can be cancelled, and only by the requester.
- Cancel runs in one transaction: lock the request row (`SELECT … FOR UPDATE`), re-check that status is still `Pending` (else **409** `ALREADY_ACTIONED`), then set `Cancelled`.
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

| Rule | HTTP | Error code |
|---|---|---|
| `end_date < start_date` | 422 | `INVALID_DATE_RANGE` |
| Range contains zero working days | 422 | `NO_WORKING_DAYS` |
| Range spans more than one calendar year (must be split into two requests) | 422 | `SPANS_MULTIPLE_YEARS` |
| Dates are not in the **current calendar year** (company timezone) | 422 | `NOT_CURRENT_YEAR` |
| Range overlaps any of the user's own **Pending or Approved** requests (any leave type) | 409 | `OVERLAPPING_REQUEST` |
| `days > available` for that type and year | 409 | `INSUFFICIENT_BALANCE` |

Validation runs **top to bottom** in this table; the first failing rule is returned.

Submit runs in **one database transaction**:

1. Lock the user's balance row for that type/year (`SELECT … FOR UPDATE`). If it does not exist, create it first with `INSERT … ON CONFLICT DO NOTHING`, then lock it.
2. Check for overlap, then `days ≤ available` (table order).
3. Insert the request as `Pending`.

- Backdating within the current year is allowed for both types.
- Rejected and Cancelled requests never block a new request.
- Overlap check is by date range regardless of leave type, to prevent the same day being deducted twice.

## 7. Approval rules

Performed in **one database transaction**:

1. Lock the request row (`SELECT … FOR UPDATE`), then the user's balance row for that type/year.
2. Verify approver ≠ requester, else **403** `SELF_ACTION_FORBIDDEN`. This check runs before the status check.
3. Verify status is still `Pending`, else **409** `ALREADY_ACTIONED`.
4. On approve: re-verify `used_days + days ≤ total_days`, else **409** `INSUFFICIENT_BALANCE`; increment `used_days` by `days`; set `Approved`, `decided_by`, `decided_at`, and the comment if given.
5. On reject: the **comment is required** (422 `COMMENT_REQUIRED` if empty); set `Rejected`, `decided_by`, `decided_at`, and the comment.

There is one comment field, stored in `decision_comment`: optional on approve, required on reject.

**Lock order everywhere:** request row first, then balance row.

Two managers acting simultaneously: the second gets 409. The approval balance check is a safety net, since submit already reserves pending days.

The `CHECK (used_days >= 0 AND used_days <= total_days)` on `leave_balances` backs up the application check so `used` can never exceed `entitlement`.

## 8. Authentication and user management

- Email + password; passwords hashed with **Argon2 via `pwdlib`**; JWT bearer tokens issued with **PyJWT**, **60-minute expiry**, signed with `SECRET_KEY` read from the environment.
- **Signup (employees only):** public page requiring a company **join code** compared to the `SIGNUP_CODE` environment variable (documented in `.env.example` and README, never hard-coded). Wrong or missing code returns a generic error.
  - Password must be at least 8 characters.
  - Emails are lowercased before they are stored or looked up (signup and login).
  - Role is set server-side to EMPLOYEE; the client can never supply it.
  - Server generates a unique `employee_code` (`EMP-0001` style).
  - Server creates 12 Earned + 10 Sick balance rows for the current calendar year.
  - Server assigns a random manager (see section 2).
- **Managers:** created only by an **idempotent seed script** (safe to run twice), never via signup or UI.
  - Seed a super manager, 2 managers that report to the super manager (so each manager's leave has someone to approve it), and 4 demo employees.
  - The seed also sets `manager_id` on users that already exist, so re-running it repairs the hierarchy.
  - Seeded users have known demo passwords and the same balance rows as signed-up users:

    | Role | Email | Password |
    |---|---|---|
    | Super manager | `supermanager@example.com` | `Manager@123` |
    | Manager | `manager1@example.com` | `Manager@123` |
    | Manager | `manager2@example.com` | `Manager@123` |
    | Employee | `employee1@example.com` | `Employee@123` |
    | Employee | `employee2@example.com` | `Employee@123` |
    | Employee | `employee3@example.com` | `Employee@123` |
    | Employee | `employee4@example.com` | `Employee@123` |

    Managers: `manager1` and `manager2` report to `supermanager`. `employee1` and `employee3` report to `manager1`; `employee2` and `employee4` to `manager2`. The assigned manager is shown on screen but is informational: any manager may still decide an employee's request.
- No admin UI, no role promotion, no password reset in the MVP.

## 9. API (indicative)

| Method & path | Who | Purpose |
|---|---|---|
| `POST /auth/signup` | public | Employee signup with join code |
| `POST /auth/login` | public | Returns JWT |
| `GET /me` | any | Profile, role and `manager_name` (null without a manager) |
| `GET /balances` | any | Own balances for current year (entitlement, used, pending, available); creates missing current-year rows |
| `POST /leave-requests` | any except the super manager | Submit |
| `GET /leave-requests` | any | Own requests (filter by status) |
| `GET /leave-requests/{id}` | owner or any manager | Request detail |
| `POST /leave-requests/{id}/cancel` | requester | Cancel Pending |
| `GET /manager/requests?status=` | manager | Pending queue and history; never returns the caller's own requests or manager requests the caller cannot act on; each pending-queue row includes `employee_available` for the request's leave type |
| `POST /leave-requests/{id}/approve` | manager (a manager's request: only their manager) | Approve (optional comment) |
| `POST /leave-requests/{id}/reject` | manager (a manager's request: only their manager) | Reject (comment required) |

Request responses include the requester's `name` and `employee_code` and the approver's name.

Errors use a consistent JSON shape `{ "code": "...", "message": "..." }` with 403 role violations, 409 conflicts (overlap, insufficient balance, already actioned), 422 validation. Besides the §6 codes, approve/reject/cancel use `ALREADY_ACTIONED` (409), `SELF_ACTION_FORBIDDEN` (403) and `COMMENT_REQUIRED` (422).

Role checks and the "not your own request" check are enforced **server-side**, not only in the UI.

## 10. Frontend (React + Vite, plain JS)

**Employee**
- Login, signup (with join code)
- Dashboard: Earned and Sick balances (entitlement / used / pending / available)
- New request form with live working-day count and inline server errors
- My requests list with status badges, manager's decision comment, and a Cancel button on Pending only
- Request detail view (own requests; managers can open any request)

**Manager** (in addition to the employee screens)
- "My leave" page: the manager's own balances, new request form and own requests
- Pending queue, oldest first: employee, type, dates, days, employee's available balance for that type (`employee_available`), Approve (optional comment) / Reject (comment required)
- All-requests history with a filter by status only
- Own requests appear only on "My leave", never in the actionable queue

## 11. Data model (PostgreSQL)

- `users`: id, employee_code (unique), name, email (unique), password_hash, role (`EMPLOYEE`|`MANAGER`), `manager_id` (nullable FK to users.id, `ON DELETE SET NULL`, `CHECK (manager_id <> id)`), created_at
- `leave_balances`: user_id, leave_type, year, `total_days`, `used_days` (both stored); unique (user_id, leave_type, year); `CHECK (used_days >= 0 AND used_days <= total_days)`. `used_days` changes only on approval; `pending` is computed as a `SUM` of Pending requests.
- `leave_requests`: fields in section 4; CHECK `end_date >= start_date`, CHECK `days > 0`, `CHECK (decided_by <> user_id)`, indexes on (user_id, status), (status), (start_date, end_date)
- Overlap protection (mandatory): PostgreSQL exclusion constraint using the `btree_gist` extension: `EXCLUDE USING gist (user_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status IN ('PENDING','APPROVED'))`. A violation (SQLSTATE `23P01`) is mapped to **409**.
- Migrations via Alembic (or equivalent).

## 12. Testing and acceptance

Backend tests must cover:
- Working-day count: weekdays only, weekend-only rejected, single day, range across weekends
- Insufficient balance at submit (including pending reservation) and at approval
- Overlap with Pending and Approved blocked; Rejected/Cancelled not blocking; cross-type overlap blocked
- Year-boundary and out-of-year rejection
- Cancel allowed only for Pending and only by owner
- Approve/reject by non-manager (403), by requester-manager (403), on already-actioned request (409), reject without comment (422)
- A manager's request: decided by their manager (200), by any other manager (403 `NOT_REQUESTERS_MANAGER`, before the 409); hidden from other managers' queue and history
- The super manager cannot submit leave (403 `MANAGER_HAS_NO_MANAGER`); signup assigns `manager1` or `manager2`; the seed assigns the hierarchy and is idempotent
- Concurrent approvals never drive `used` above entitlement:
  - the same request approved twice at once: one succeeds, the other gets 409 `ALREADY_ACTIONED`
  - two requests that both fit the balance, approved at once: both succeed and `used_days` is correct
  - a forced impossible state (balance altered directly so an approval would exceed `total_days`): approval gets 409 `INSUFFICIENT_BALANCE` and `used_days` is unchanged
- Concurrent submits by the same user never over-reserve the balance or create overlapping Pending/Approved requests
- Cancel-vs-approve race on the same request: exactly one succeeds, the other gets 409 `ALREADY_ACTIONED`
- The three DB constraints reject direct invalid writes: the `leave_balances` `used_days` CHECK, the overlap exclusion constraint (`23P01`), and `CHECK (decided_by <> user_id)`
- Signup: wrong/missing code rejected, role cannot be injected, balances and employee_code created
- Seed script idempotent

Acceptance: a seeded manager and employee can complete submit, approve, reject and cancel flows end-to-end in the browser against PostgreSQL.

## 13. Assumptions

1. Single company, one fixed timezone (`Asia/Kolkata`); "today" and "current year" are derived in it through a single helper.
2. Dates are plain calendar dates with no time component.
3. Pending days are reserved against `available` at submit time; `used` only changes on approval.
4. Any manager can act on any employee request. A manager's request can be decided only by their own manager (`manager_id`); the super manager (no manager) cannot submit leave. There is no priority or escalation; an employee's manager is informational.
5. Managers have their own balances and can submit leave, approved by their manager. The super manager has balances but cannot take leave.
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
- Delegation, escalation, multi-level approval, and routing employee requests to the employee's manager only
- Admin UI, role promotion, user deactivation, manager reassignment
- Password reset, email verification, SSO, MFA, verified invitation links
- Email/Slack notifications, audit-log UI, exports/reports, attachments (e.g. medical certificates)
- Per-employee work schedules, multiple timezones, localisation
- Mobile apps; responsive web is best-effort

## 15. Known limitations (to improve next)

- Shared join code (not per-person); no email verification
- No admin UI or role promotion; managers and their assignments only via seed (signup assigns a random manager)
- The super manager cannot take leave
- Approved leave cannot be undone without a manual DB fix
- Pending requests are not auto-expired and may sit indefinitely
- No team calendar (month view of Approved leave across employees)

## 16. README

The README must contain these sections: setup, stack, architecture, data model, assumptions, limitations.
