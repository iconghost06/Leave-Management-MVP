import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/endpoints.js";
import BalanceCards from "../components/BalanceCards.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";
import RequestsTable from "../components/RequestsTable.jsx";

const RECENT_COUNT = 5;

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // The list comes back newest first (created_at desc), so the first 5 are the most recent.
    Promise.all([api.getBalances(), api.listLeaveRequests()])
      .then(([balances, requests]) => {
        if (!cancelled) setData({ balances, recent: requests.slice(0, RECENT_COUNT) });
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
  }, []);

  return (
    <section>
      <h1>Dashboard</h1>
      <ErrorBanner error={error} />
      {loading && <p className="page-message">Loading...</p>}
      {data && (
        <>
          <BalanceCards balances={data.balances.balances} year={data.balances.year} />
          <div className="section-header">
            <h2>Recent requests</h2>
            <Link to="/requests/new">New request</Link>
          </div>
          {data.recent.length === 0 ? (
            <p className="empty-state">No requests yet</p>
          ) : (
            <>
              <RequestsTable requests={data.recent} />
              <p>
                <Link to="/requests">View all requests</Link>
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
