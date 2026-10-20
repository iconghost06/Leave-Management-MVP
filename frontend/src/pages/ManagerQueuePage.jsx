import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/endpoints.js";
import DecisionDialog from "../components/DecisionDialog.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";
import { CLOSING_ERRORS } from "../utils/decisionErrors.js";
import { leaveTypeLabel } from "../utils/labels.js";

export default function ManagerQueuePage() {
  const [requests, setRequests] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [loading, setLoading] = useState(true);
  // { action: "approve" | "reject", request } while the dialog is open.
  const [dialog, setDialog] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState(null);
  // Bumping this re-runs the load effect, which is how the queue refreshes after a decision.
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .listManagerRequests("PENDING")
      .then((result) => {
        if (cancelled) return;
        setRequests(result);
        setLoadError(null);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadCount]);

  function openDialog(action, request) {
    setDialogError(null);
    setDialog({ action, request });
  }

  const closeDialog = useCallback(() => setDialog(null), []);

  async function handleConfirm(comment) {
    const { action, request } = dialog;
    setSubmitting(true);
    setDialogError(null);
    try {
      if (action === "approve") await api.approveLeaveRequest(request.id, comment);
      else await api.rejectLeaveRequest(request.id, comment);
      setActionError(null);
      setDialog(null);
    } catch (err) {
      const message = CLOSING_ERRORS[err.code];
      if (message) {
        setActionError({ message });
        setDialog(null);
      } else {
        setDialogError(err);
        setSubmitting(false);
        return;
      }
    }
    setSubmitting(false);
    setReloadCount((n) => n + 1);
  }

  return (
    <section>
      <h1>Pending queue</h1>
      <ErrorBanner error={actionError} />
      <ErrorBanner error={loadError} />
      {loading && !requests && <p className="page-message">Loading...</p>}
      {requests &&
        (requests.length === 0 ? (
          <p className="empty-state">No pending requests</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Assigned manager</th>
                  <th>Type</th>
                  <th>Dates</th>
                  <th>Days</th>
                  <th>Reason</th>
                  <th>Available (after pending)</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {requests.map((request) => (
                  <tr key={request.id}>
                    <td>
                      {request.requester_name}
                      <div className="field-hint">{request.requester_employee_code}</div>
                    </td>
                    <td>{request.employee_manager_name}</td>
                    <td>{leaveTypeLabel(request.leave_type)}</td>
                    <td>
                      {request.start_date}
                      {request.end_date !== request.start_date && ` to ${request.end_date}`}
                    </td>
                    <td>{request.days}</td>
                    <td>{request.reason || "-"}</td>
                    <td>{request.employee_available}</td>
                    <td className="row-actions">
                      <Link to={`/requests/${request.id}`}>Details</Link>
                      <button type="button" onClick={() => openDialog("approve", request)}>
                        Approve
                      </button>
                      <button type="button" className="button-danger" onClick={() => openDialog("reject", request)}>
                        Reject
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      {dialog && (
        <DecisionDialog
          action={dialog.action}
          request={dialog.request}
          submitting={submitting}
          error={dialogError}
          onConfirm={handleConfirm}
          onCancel={closeDialog}
        />
      )}
    </section>
  );
}
