import { leaveTypeLabel } from "../utils/labels.js";

export default function BalanceCards({ balances, year }) {
  return (
    <div className="cards" aria-label={`Leave balances for ${year}`}>
      {balances.map((balance) => (
        <article key={balance.leave_type} className="card">
          <h2>{leaveTypeLabel(balance.leave_type)} leave</h2>
          <p className="card-available">
            {balance.available}
            <span> days available</span>
          </p>
          <dl className="card-details">
            <div>
              <dt>Total</dt>
              <dd>{balance.entitlement}</dd>
            </div>
            <div>
              <dt>Used</dt>
              <dd>{balance.used}</dd>
            </div>
            <div>
              <dt>Pending</dt>
              <dd>{balance.pending}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}
