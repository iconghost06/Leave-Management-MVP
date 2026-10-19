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
