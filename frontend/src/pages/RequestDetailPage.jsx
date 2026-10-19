import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api/endpoints.js";
import ErrorBanner from "../components/ErrorBanner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { leaveTypeLabel } from "../utils/labels.js";

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

export default function RequestDetailPage() {
  const { id } = useParams();
  const [request, setRequest] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setRequest(null);
    setError(null);
    api
      .getLeaveRequest(id)
      .then((result) => {
        if (!cancelled) setRequest(result);
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
  }, [id]);

  return (
    <section>
      <p>
        <Link to="/requests">Back to my requests</Link>
      </p>
      <h1>Request details</h1>
      {/* 403 FORBIDDEN (someone else's request) and 404 NOT_FOUND arrive here with their message. */}
      <ErrorBanner error={error} />
      {loading && <p className="page-message">Loading...</p>}
      {request && (
        <dl className="detail">
          <dt>Employee</dt>
          <dd>
            {request.requester_name} ({request.requester_employee_code})
          </dd>
          <dt>Leave type</dt>
          <dd>{leaveTypeLabel(request.leave_type)}</dd>
          <dt>Dates</dt>
          <dd>
            {request.start_date} to {request.end_date}
          </dd>
          <dt>Working days</dt>
          <dd>{request.days}</dd>
          <dt>Status</dt>
          <dd>
            <StatusBadge status={request.status} />
          </dd>
          <dt>Reason</dt>
          <dd>{request.reason || "-"}</dd>
          <dt>Submitted</dt>
          <dd>{formatDateTime(request.created_at)}</dd>
          {request.decided_at && (
            <>
              <dt>Decided by</dt>
              <dd>{request.decided_by_name || "-"}</dd>
              <dt>Decided at</dt>
              <dd>{formatDateTime(request.decided_at)}</dd>
            </>
          )}
          <dt>Decision comment</dt>
          <dd>{request.decision_comment || "-"}</dd>
        </dl>
      )}
    </section>
  );
}
