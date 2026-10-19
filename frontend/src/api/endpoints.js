import { request } from "./client.js";

export function login(email, password) {
  return request("POST", "/auth/login", { email, password });
}

export function signup(name, email, password, joinCode) {
  return request("POST", "/auth/signup", { name, email, password, join_code: joinCode });
}

export function getMe() {
  return request("GET", "/me");
}

export function getBalances() {
  return request("GET", "/balances");
}

export function createLeaveRequest(leaveType, startDate, endDate, reason) {
  return request("POST", "/leave-requests", {
    leave_type: leaveType,
    start_date: startDate,
    end_date: endDate,
    reason: reason || null,
  });
}

export function listLeaveRequests(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request("GET", `/leave-requests${query}`);
}

export function getLeaveRequest(id) {
  return request("GET", `/leave-requests/${encodeURIComponent(id)}`);
}

export function cancelLeaveRequest(id) {
  return request("POST", `/leave-requests/${encodeURIComponent(id)}/cancel`);
}

export function listManagerRequests(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request("GET", `/manager/requests${query}`);
}

export function approveLeaveRequest(id, comment) {
  return request("POST", `/leave-requests/${encodeURIComponent(id)}/approve`, {
    comment: comment || null,
  });
}

export function rejectLeaveRequest(id, comment) {
  return request("POST", `/leave-requests/${encodeURIComponent(id)}/reject`, {
    comment: comment || null,
  });
}
