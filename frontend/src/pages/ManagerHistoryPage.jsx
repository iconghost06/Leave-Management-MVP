import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import * as api from "../api/endpoints.js";
import ErrorBanner from "../components/ErrorBanner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { leaveTypeLabel } from "../utils/labels.js";

const STATUSES = ["APPROVED", "REJECTED", "CANCELLED"];

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

export default function ManagerHistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = STATUSES.includes(searchParams.get("status")) ? searchParams.get("status") : "";

  const [requests, setRequests] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listManagerRequests(status)
      .then((result) => {
        if (cancelled) return;
        // "All" has no status param, so PENDING rows come back too. They belong to the queue.
        setRequests(result.filter((request) => request.status !== "PENDING"));
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
  }, [status]);

  function handleFilter(event) {
    const value = event.target.value;
    setSearchParams(value ? { status: value } : {});
  }

  return (
    <section>
      <h1>History</h1>
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
      {loading && <p className="page-message">Loading...</p>}
      {!loading &&
        requests &&
        (requests.length === 0 ? (
          <p className="empty-state">{status ? `No ${status.toLowerCase()} requests` : "No decided requests yet"}</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Requester</th>
                  <th>Assigned manager</th>
                  <th>Type</th>
                  <th>Dates</th>
                  <th>Days</th>
                  <th>Status</th>
                  <th>Decided by</th>
                  <th>Decided at</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {requests.map((request) => (
                  <tr key={request.id}>
                    <td>
                      {request.requester_name}{" "}
                      <span className="role-tag">
                        {request.requester_role === "MANAGER" ? "Manager" : "Employee"}
                      </span>
                      <div className="field-hint">{request.requester_employee_code}</div>
                    </td>
                    <td>{request.employee_manager_name}</td>
                    <td>{leaveTypeLabel(request.leave_type)}</td>
                    <td>
                      {request.start_date}
                      {request.end_date !== request.start_date && ` to ${request.end_date}`}
                    </td>
                    <td>{request.days}</td>
                    <td>
                      <StatusBadge status={request.status} />
                    </td>
                    <td>{request.decided_by_name || "-"}</td>
                    <td>{formatDateTime(request.decided_at)}</td>
                    <td className="row-actions">
                      <Link to={`/requests/${request.id}`}>Details</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}
