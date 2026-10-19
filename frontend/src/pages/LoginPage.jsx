import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { homePathFor, useAuth } from "../auth/AuthContext.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";

const SLOW_AFTER_MS = 5000;

export default function LoginPage() {
  const { login, isLoggedIn, role, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState(null);

  // After 5 s of waiting, show the cold-start hint. The timer is cleared as soon as the
  // request ends (or the page unmounts).
  useEffect(() => {
    if (!submitting) return undefined;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [submitting]);

  if (!loading && isLoggedIn) return <Navigate to={homePathFor(role)} replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      navigate(homePathFor(user.role), { replace: true });
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <h1>Log in</h1>
      <form onSubmit={handleSubmit}>
        <ErrorBanner error={error} />
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in..." : "Log in"}
        </button>
        {submitting && slow && (
          <p className="hint">The server may be waking up, please wait.</p>
        )}
      </form>
      <p>
        New employee? <Link to="/signup">Sign up</Link>
      </p>
    </main>
  );
}
