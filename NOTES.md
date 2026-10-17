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
