// The only file that calls fetch(). Every backend request goes through apiFetch, so the
// base URL, the login header and error handling live in one place.
import { reportError } from "@/utils/reportError";

// Public by design: everything in a frontend bundle can be read by anyone. Never put secrets here.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const NETWORK_MESSAGE = "Can't reach the server. Check your connection and try again.";
const UNAVAILABLE_MESSAGE = "Service temporarily unavailable, please try again.";
const UNEXPECTED_MESSAGE = "Something went wrong on this page. Please try again.";

// One error type for every failed request.
//   status:     HTTP status, or 0 when no response arrived (network down, CORS refused)
//   retryAfter: seconds from the Retry-After header (429), or null
//   errors:     row problems from the FAQ upload's 422: [{row, field, message}]
export class ApiError extends Error {
  constructor(status, message, retryAfter = null, errors = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
    this.errors = errors;
  }
}

// AuthContext registers a function here that logs the owner out. It runs when a request
// that carried an owner token gets 401 (expired or invalid token).
let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function apiFetch(path, { method = "GET", body, token } = {}) {
  // A FormData body (file upload) is sent as it is: the browser sets the multipart
  // Content-Type with its boundary. Anything else is sent as JSON.
  const isForm = body instanceof FormData;
  const headers = {};
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(API_BASE_URL + path, {
      method,
      headers,
      body: body === undefined || isForm ? body : JSON.stringify(body),
    });
  } catch {
    // fetch only throws when there is no HTTP response at all.
    throw new ApiError(0, NETWORK_MESSAGE);
  }

  const data = await readJson(response);

  if (!response.ok) {
    if (response.status === 401 && token && onUnauthorized) onUnauthorized();
    const rowErrors = Array.isArray(data?.errors) ? data.errors : [];
    throw new ApiError(
      response.status,
      errorMessage(response.status, data),
      retryAfterSeconds(response),
      rowErrors,
    );
  }
  return data;
}

// Hooks call this on anything they catch: an ApiError passes through, anything else is a
// bug in our code, so it is reported and replaced by a message a person can read.
export function asApiError(error) {
  if (error instanceof ApiError) return error;
  reportError(error, { source: "request" });
  return new ApiError(0, UNEXPECTED_MESSAGE);
}

// The parsed JSON body, or null when the body is empty or not JSON (e.g. a plain-text 502).
async function readJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// FastAPI errors look like {"detail": "text"} or, for request validation,
// {"detail": [{"msg": "..."}, ...]}. Show the server's words; invent text only if there are none.
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
