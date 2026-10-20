import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import * as api from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import DecisionDialog from "../components/DecisionDialog.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { CLOSING_ERRORS } from "../utils/decisionErrors.js";
import { leaveTypeLabel } from "../utils/labels.js";

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

export default function RequestDetailPage() {
  const { id } = useParams();
  const { user, role, isSuperManager } = useAuth();
  const [request, setRequest] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState(null);
  // "approve" | "reject" while the dialog is open.
  const [dialogAction, setDialogAction] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState(null);
  // Bumping this re-runs the load effect, which is how the page refreshes after a decision.
  const [reloadCount, setReloadCount] = useState(0);

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
  }, [id, reloadCount]);

  // UX only: the server enforces the role, the self check and the PENDING check again.
  const isOwn = request ? request.user_id === user?.id : true;
  const canDecide = role === "MANAGER" && request?.status === "PENDING" && !isOwn;

  const closeDialog = useCallback(() => setDialogAction(null), []);

  function openDialog(action) {
    setDialogError(null);
    setDialogAction(action);
  }

  async function handleConfirm(comment) {
    setSubmitting(true);
    setDialogError(null);
    try {
      if (dialogAction === "approve") await api.approveLeaveRequest(request.id, comment);
      else await api.rejectLeaveRequest(request.id, comment);
      setActionError(null);
      setDialogAction(null);
    } catch (err) {
      const message = CLOSING_ERRORS[err.code];
      if (message) {
        setActionError({ message });
        setDialogAction(null);
      } else {
        setDialogError(err);
        setSubmitting(false);
        return;
      }
    }
    setSubmitting(false);
    setReloadCount((n) => n + 1);
  }

  // The super manager has no requests of their own, so an own-request URL goes to the queue.
  if (isSuperManager && request && isOwn) return <Navigate to="/manager/queue" replace />;

  return (
    <section>
      <p>
        {request && !isOwn ? (
          <Link to="/manager/queue">Back to queue</Link>
        ) : (
          <Link to="/requests">Back to my requests</Link>
        )}
      </p>
      <h1>Request details</h1>
      {/* 403 FORBIDDEN (someone else's request) and 404 NOT_FOUND arrive here with their message. */}
      <ErrorBanner error={actionError} />
      <ErrorBanner error={error} />
      {loading && <p className="page-message">Loading...</p>}
      {request && (
        <>
          <dl className="detail">
            <dt>Employee</dt>
            <dd>
              {request.requester_name} ({request.requester_employee_code})
            </dd>
            {isOwn && user?.manager_name && (
              <>
                <dt>Sent to</dt>
                <dd>{user.manager_name}</dd>
              </>
            )}
            {!isOwn && request.employee_manager_name && (
              <>
                <dt>Assigned manager</dt>
                <dd>{request.employee_manager_name}</dd>
              </>
            )}
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
          {canDecide && (
            <div className="detail-actions">
              <button type="button" onClick={() => openDialog("approve")}>
                Approve
              </button>
              <button type="button" className="button-danger" onClick={() => openDialog("reject")}>
                Reject
              </button>
            </div>
          )}
        </>
      )}
      {dialogAction && request && (
        <DecisionDialog
          action={dialogAction}
          request={request}
          submitting={submitting}
          error={dialogError}
          onConfirm={handleConfirm}
          onCancel={closeDialog}
        />
      )}
    </section>
  );
}
