import { Link } from "react-router-dom";
import { leaveTypeLabel } from "../utils/labels.js";
import StatusBadge from "./StatusBadge.jsx";

// Renders the rows it is given. The Cancel column exists only when the page passes onCancel,
// and the button only on PENDING rows (R13). The page owns the confirm and the refresh.
export default function RequestsTable({ requests, onCancel, cancellingId }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Dates</th>
            <th>Days</th>
            <th>Status</th>
            <th>Decision comment</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {requests.map((request) => (
            <tr key={request.id}>
              <td>{leaveTypeLabel(request.leave_type)}</td>
              <td>
                {request.start_date}
                {request.end_date !== request.start_date && ` to ${request.end_date}`}
              </td>
              <td>{request.days}</td>
              <td>
                <StatusBadge status={request.status} />
              </td>
              <td>{request.decision_comment || "-"}</td>
              <td className="row-actions">
                <Link to={`/requests/${request.id}`}>Details</Link>
                {onCancel && request.status === "PENDING" && (
                  <button
                    type="button"
                    className="button-danger"
                    disabled={cancellingId === request.id}
                    onClick={() => onCancel(request)}
                  >
                    {cancellingId === request.id ? "Cancelling..." : "Cancel"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
