// Owner accounts: sign up, log in, and "who am I" for a saved token.
import { apiFetch } from "./client";

// Same limits as app/services/accounts.py, so forms can warn before sending.
export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;
export const MAX_BUSINESS_NAME_LENGTH = 200;

// Sends {email, password, business_name}. Returns the account: {id, email, business_name}.
// Errors: 409 email already used, 422 a rule broken (message from the server).
export function register({ email, password, businessName }) {
  return apiFetch("/auth/register", {
    method: "POST",
    body: { email, password, business_name: businessName },
  });
}

// Returns {access_token, token_type: "bearer", expires_in (seconds)}. 401 = wrong email or password.
export function login({ email, password }) {
  return apiFetch("/auth/login", { method: "POST", body: { email, password } });
}

// Returns the account that owns the token: {id, email, business_name}. 401 = token no longer valid.
export function getMe(token) {
  return apiFetch("/auth/me", { token });
}
