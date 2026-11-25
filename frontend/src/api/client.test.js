// Tests for the API client: how responses become data or one readable ApiError.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, asApiError, setUnauthorizedHandler } from "./client";

function reply(status, body, headers = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return new Response(text, { status, headers });
}

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  setUnauthorizedHandler(null);
});

describe("apiFetch", () => {
  it("returns parsed JSON and sends JSON bodies with the token", async () => {
    fetch.mockResolvedValue(reply(200, { ok: true }));

    const data = await apiFetch("/x", { method: "POST", body: { a: 1 }, token: "t" });

    expect(data).toEqual({ ok: true });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("http://localhost:8000/x");
    expect(options.headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer t",
    });
    expect(options.body).toBe('{"a":1}');
  });

  it.each([
    [
      409,
      { detail: "An account with this email already exists" },
      "An account with this email already exists",
    ],
    [
      422,
      { detail: [{ msg: "Value error, name too long" }, { msg: "bad" }] },
      "name too long. bad",
    ],
    [502, "Bad Gateway", "Service temporarily unavailable, please try again."],
    [418, "", "Request failed (HTTP 418)."],
  ])("turns a %i response into one readable message", async (status, body, message) => {
    fetch.mockResolvedValue(reply(status, body));

    const error = await apiFetch("/x").catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.message]).toEqual([status, message]);
  });

  it("keeps row errors and Retry-After", async () => {
    const rows = [{ row: 2, field: "answer", message: "must not be empty" }];
    fetch.mockResolvedValue(reply(429, { detail: "slow", errors: rows }, { "Retry-After": "7" }));

    const error = await apiFetch("/x").catch((caught) => caught);

    expect(error.retryAfter).toBe(7);
    expect(error.errors).toEqual(rows);
  });

  it("reports a network failure as status 0", async () => {
    fetch.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await apiFetch("/x").catch((caught) => caught);

    expect(error.status).toBe(0);
    expect(error.message).toMatch(/^Can't reach the server/);
  });

  it("calls the logout handler on 401 only when a token was sent", async () => {
    const logout = vi.fn();
    setUnauthorizedHandler(logout);

    fetch.mockResolvedValue(reply(401, { detail: "Incorrect email or password" }));
    await apiFetch("/auth/login").catch(() => {});
    expect(logout).not.toHaveBeenCalled();

    fetch.mockResolvedValue(reply(401, { detail: "Not authenticated" }));
    await apiFetch("/faq", { token: "expired" }).catch(() => {});
    expect(logout).toHaveBeenCalledTimes(1);
  });
});

describe("asApiError", () => {
  it("passes ApiErrors through and hides other errors behind a readable message", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const known = new ApiError(400, "nope");

    expect(asApiError(known)).toBe(known);
    const hidden = asApiError(new TypeError("x is undefined"));
    expect(hidden.status).toBe(0);
    expect(hidden.message).toBe("Something went wrong on this page. Please try again.");
    expect(console.error).toHaveBeenCalled();
  });
});
