import { apiFetch } from "./client.js";

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;
export const MAX_BUSINESS_NAME_LENGTH = 200;

export function register({ email, password, businessName }) {
  return apiFetch("/auth/register", {
    method: "POST",
    body: { email, password, business_name: businessName },
  });
}

export function login({ email, password }) {
  return apiFetch("/auth/login", { method: "POST", body: { email, password } });
}

export function getMe(token) {
  return apiFetch("/auth/me", { token });
}
