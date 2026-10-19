import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { clearToken, getToken, setToken, setUnauthorizedHandler } from "../api/client.js";
import * as api from "../api/endpoints.js";

const AuthContext = createContext(null);

export function homePathFor(role) {
  return role === "MANAGER" ? "/manager/queue" : "/dashboard";
}

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  // True while the boot-time /me call is running, so guards do not redirect too early.
  const [loading, setLoading] = useState(() => Boolean(getToken()));

  // A 401 anywhere (client.js has already cleared the token): drop the user, go to /login.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      navigate("/login", { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  // On boot, a stored token is exchanged for the user via /me.
  useEffect(() => {
    if (!getToken()) return undefined;
    let cancelled = false;
    api
      .getMe()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // A 401 was already handled by client.js. Other failures leave the user logged out.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Store the token, then load the user (role comes from /me, which reads the DB row).
  const finishAuth = useCallback(async (tokenResponse) => {
    setToken(tokenResponse.access_token);
    try {
      const me = await api.getMe();
      setUser(me);
      return me;
    } catch (err) {
      clearToken();
      throw err;
    }
  }, []);

  const login = useCallback(
    async (email, password) => finishAuth(await api.login(email, password)),
    [finishAuth],
  );

  const signup = useCallback(
    async (name, email, password, joinCode) =>
      finishAuth(await api.signup(name, email, password, joinCode)),
    [finishAuth],
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  // The token is read on every render, so removing it in devtools logs the user out on the
  // next navigation, even though `user` is still in memory.
  const isLoggedIn = Boolean(user) && Boolean(getToken());
  // The super manager is a MANAGER with no manager (/me has manager_name null). They cannot take
  // leave, so they have no personal pages.
  const isSuperManager = user?.role === "MANAGER" && user.manager_name == null;

  const value = {
    user,
    role: user?.role ?? null,
    isSuperManager,
    isLoggedIn,
    loading,
    login,
    signup,
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

// Route guards are UX only; the server enforces every rule.
export function RequireAuth() {
  const { isLoggedIn, loading } = useAuth();
  if (loading) return <p className="page-message">Loading...</p>;
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function RequireManager() {
  const { role } = useAuth();
  if (role !== "MANAGER") return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

// The super manager has no leave of their own, so the personal pages send them to the queue.
export function RequireNotSuperManager() {
  const { isSuperManager } = useAuth();
  if (isSuperManager) return <Navigate to="/manager/queue" replace />;
  return <Outlet />;
}
