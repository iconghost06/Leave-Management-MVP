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

## Step 1.2

_Summary written by Claude Code, to be replaced with my own words._

- Added signup, login and `GET /me`. A token is minted at login and checked by `get_current_user`, which then loads the user row from the database.
- The role is always read from that database row, never from the token, so a forged or out-of-date `role` claim cannot make someone a manager (R14, R22).
- Signup checks the join code first, in constant time, before any validation or database access, so a wrong or missing code gets the same `SIGNUP_FAILED` body and nobody can probe emails (A2). The signup schema has no `role` field, so a role sent by the client is dropped and new users are always EMPLOYEE (A3). Emails are lowercased on signup and login (A5).
- The seed is the only way a manager is created. It checks each email before inserting and never edits existing users, so a second run creates nothing (E1, E2, R23). Each user also gets 12 Earned + 10 Sick balance rows through `ensure_balance_rows`.
