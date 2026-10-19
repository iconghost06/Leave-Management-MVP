const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "token";

// Paths whose errors (including 401 INVALID_CREDENTIALS) are shown inline by the page.
const INLINE_ERROR_PATHS = ["/auth/login", "/auth/signup"];

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // storage unavailable: the session lasts until the page is closed
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // nothing to clear
  }
}

// AuthContext registers a callback that drops its user and navigates to /login.
let onUnauthorized = null;
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function request(method, path, body) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the server. Please try again.");
  }

  if (response.ok) {
    return response.status === 204 ? null : response.json();
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // body was not JSON
  }
  const error = new ApiError(
    response.status,
    payload?.code || "UNKNOWN_ERROR",
    typeof payload?.message === "string" ? payload.message : "Something went wrong.",
  );

  if (response.status === 401 && !INLINE_ERROR_PATHS.includes(path)) {
    clearToken();
    if (onUnauthorized) onUnauthorized();
  }
  throw error;
}
