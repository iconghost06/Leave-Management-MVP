import { useEffect, useState } from "react";
import { leaveTypeLabel } from "../utils/labels.js";
import ErrorBanner from "./ErrorBanner.jsx";

// Confirm dialog for one approve or reject. It only collects the comment: the page calls the API
// and passes back `submitting` and `error`. Reject needs a comment, but the server checks that
// (COMMENT_REQUIRED) and the error is shown here, so the dialog stays open for the manager to fix it.
export default function DecisionDialog({ action, request, submitting, error, onConfirm, onCancel }) {
  const [comment, setComment] = useState("");
  const isReject = action === "reject";

  useEffect(() => {
    function handleKey(event) {
      if (event.key === "Escape" && !submitting) onCancel();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [submitting, onCancel]);

  function handleSubmit(event) {
    event.preventDefault();
    onConfirm(comment.trim());
  }

  return (
    <div className="dialog-backdrop">
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" onSubmit={handleSubmit}>
        <h2 id="dialog-title">{isReject ? "Reject" : "Approve"} this request?</h2>
        <p className="dialog-summary">
          {request.requester_name}: {leaveTypeLabel(request.leave_type)}, {request.start_date}
          {request.end_date !== request.start_date && ` to ${request.end_date}`} ({request.days}{" "}
          {request.days === 1 ? "day" : "days"})
        </p>
        <ErrorBanner error={error} />
        <label>
          {isReject ? "Reason (required to reject)" : "Comment (optional)"}
          <textarea
            rows={3}
            maxLength={500}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            autoFocus
          />
        </label>
        <div className="dialog-actions">
          <button type="button" className="button-secondary" disabled={submitting} onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className={isReject ? "button-danger" : ""} disabled={submitting}>
            {submitting ? "Saving..." : isReject ? "Reject" : "Approve"}
          </button>
        </div>
      </form>
    </div>
  );
}
