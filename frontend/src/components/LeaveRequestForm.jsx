import { useState } from "react";
import { countWorkingDays } from "../utils/workingDays.js";
import { LEAVE_TYPES, leaveTypeLabel } from "../utils/labels.js";
import ErrorBanner from "./ErrorBanner.jsx";

// Server codes about the dates are shown next to the date fields; every other code (overlap,
// balance, validation, network...) goes in the banner above the form.
const DATE_ERROR_CODES = [
  "INVALID_DATE_RANGE",
  "NO_WORKING_DAYS",
  "SPANS_MULTIPLE_YEARS",
  "NOT_CURRENT_YEAR",
];

export default function LeaveRequestForm({ balances, submitting, error, onSubmit }) {
  const [leaveType, setLeaveType] = useState(LEAVE_TYPES[0]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");

  const dateError = error && DATE_ERROR_CODES.includes(error.code) ? error : null;
  const bannerError = error && !dateError ? error : null;

  // Preview only: the server counts again on submit and its answer is the one that counts.
  const days = countWorkingDays(startDate, endDate);
  const reversed = Boolean(startDate && endDate && endDate < startDate);
  const available = balances?.find((b) => b.leave_type === leaveType)?.available;

  function handleSubmit(event) {
    event.preventDefault();
    onSubmit({ leaveType, startDate, endDate, reason: reason.trim() });
  }

  return (
    <form className="request-form" onSubmit={handleSubmit}>
      <ErrorBanner error={bannerError} />
      <label>
        Leave type
        <select value={leaveType} onChange={(e) => setLeaveType(e.target.value)}>
          {LEAVE_TYPES.map((type) => (
            <option key={type} value={type}>
              {leaveTypeLabel(type)}
            </option>
          ))}
        </select>
        {available !== undefined && <span className="field-hint">{available} days available</span>}
      </label>
      <div className="form-row">
        <label>
          Start date
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
            aria-invalid={Boolean(dateError)}
          />
        </label>
        <label>
          End date
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            required
            aria-invalid={Boolean(dateError)}
          />
        </label>
      </div>
      {dateError && (
        <p className="field-error" role="alert">
          {dateError.message}
          <span className="error-code"> ({dateError.code})</span>
        </p>
      )}
      {startDate && endDate && (
        <p className="day-count" aria-live="polite">
          {reversed
            ? "The end date is before the start date."
            : `${days} working ${days === 1 ? "day" : "days"} (Mon-Fri; the server confirms on submit)`}
        </p>
      )}
      <label>
        Reason (optional)
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={500}
          rows={3}
        />
      </label>
      <button type="submit" disabled={submitting}>
        {submitting ? "Submitting..." : "Submit request"}
      </button>
    </form>
  );
}
