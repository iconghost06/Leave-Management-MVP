import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api/endpoints.js";
import LeaveRequestForm from "../components/LeaveRequestForm.jsx";

export default function NewRequestPage() {
  const navigate = useNavigate();
  const [balances, setBalances] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Only used for the "N days available" hint; a failure here must not block the form.
  useEffect(() => {
    let cancelled = false;
    api
      .getBalances()
      .then((result) => {
        if (!cancelled) setBalances(result.balances);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit({ leaveType, startDate, endDate, reason }) {
    setError(null);
    setSubmitting(true);
    try {
      await api.createLeaveRequest(leaveType, startDate, endDate, reason);
      navigate("/requests");
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h1>New request</h1>
      <LeaveRequestForm
        balances={balances}
        submitting={submitting}
        error={error}
        onSubmit={handleSubmit}
      />
    </section>
  );
}
