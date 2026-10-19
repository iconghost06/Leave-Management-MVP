import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

export default function NavBar() {
  const { user, role, logout } = useAuth();
  return (
    <header className="navbar">
      <span className="navbar-brand">Leave Management</span>
      <nav className="navbar-links">
        {role === "MANAGER" ? (
          <>
            <Link to="/manager/queue">Queue</Link>
            <Link to="/manager/history">History</Link>
            <Link to="/dashboard">My leave</Link>
          </>
        ) : (
          <>
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/requests/new">New request</Link>
            <Link to="/requests">My requests</Link>
          </>
        )}
      </nav>
      <span className="navbar-user">
        {user?.name} ({role === "MANAGER" ? "Manager" : "Employee"})
      </span>
      <button type="button" className="button-secondary" onClick={logout}>
        Log out
      </button>
    </header>
  );
}
