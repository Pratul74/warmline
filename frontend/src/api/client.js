const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

const NETWORK_MESSAGE = "Can't reach the server. Check your connection and try again.";
const UNAVAILABLE_MESSAGE = "Service temporarily unavailable, please try again.";

export class ApiError extends Error {
  constructor(status, message, retryAfter = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function apiFetch(path, { method = "GET", body, token } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(API_BASE_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {

    throw new ApiError(0, NETWORK_MESSAGE);
  }

  const data = await readJson(response);

  if (!response.ok) {
    if (response.status === 401 && token && onUnauthorized) onUnauthorized();
    throw new ApiError(response.status, errorMessage(response.status, data), retryAfterSeconds(response));
  }
  return data;
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function errorMessage(status, data) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => String(item.msg).replace(/^Value error, /, "")).join(". ");
  }
  if (status >= 500) return UNAVAILABLE_MESSAGE;
  return `Request failed (HTTP ${status}).`;
}

function retryAfterSeconds(response) {
  const value = Number(response.headers.get("Retry-After"));
  return Number.isFinite(value) && value > 0 ? value : null;
}
