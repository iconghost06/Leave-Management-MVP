import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import * as api from "../api/endpoints.js";
import ErrorBanner from "../components/ErrorBanner.jsx";
import RequestsTable from "../components/RequestsTable.jsx";

const STATUSES = ["PENDING", "APPROVED", "REJECTED", "CANCELLED"];

export default function MyRequestsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = STATUSES.includes(searchParams.get("status")) ? searchParams.get("status") : "";

  const [requests, setRequests] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cancellingId, setCancellingId] = useState(null);
  // Bumping this re-runs the load effect, which is how the list refreshes after a cancel.
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listLeaveRequests(status)
      .then((result) => {
        if (cancelled) return;
        setRequests(result);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, reloadCount]);

  const handleCancel = useCallback(async (request) => {
    if (!window.confirm("Cancel this leave request? This cannot be undone.")) return;
    setCancellingId(request.id);
    setError(null);
    try {
      await api.cancelLeaveRequest(request.id);
    } catch (err) {
      // e.g. 409 ALREADY_ACTIONED: a manager decided first. Show it, then refresh below.
      setError(err);
    }
    setCancellingId(null);
    setReloadCount((n) => n + 1);
  }, []);

  function handleFilter(event) {
    const value = event.target.value;
    setSearchParams(value ? { status: value } : {});
  }

  return (
    <section>
      <div className="section-header">
        <h1>My requests</h1>
        <Link to="/requests/new">New request</Link>
      </div>
      <label className="filter">
        Status
        <select value={status} onChange={handleFilter}>
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0) + s.slice(1).toLowerCase()}
            </option>
          ))}
        </select>
      </label>
      <ErrorBanner error={error} />
      {loading && !requests && <p className="page-message">Loading...</p>}
      {requests &&
        (requests.length === 0 ? (
          <p className="empty-state">
            {status ? `No ${status.toLowerCase()} requests` : "No requests yet"}
          </p>
        ) : (
          <RequestsTable requests={requests} onCancel={handleCancel} cancellingId={cancellingId} />
        ))}
    </section>
  );
}
