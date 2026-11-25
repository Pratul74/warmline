// Tests for the two shared hooks: loading data and submitting changes.
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { useApiRequest } from "./useApiRequest";
import { useSubmit } from "./useSubmit";

describe("useApiRequest", () => {
  it("is loading first, then has the data", async () => {
    const load = vi.fn().mockResolvedValue(["a"]);
    const { result } = renderHook(() => useApiRequest(load));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual(["a"]);
    expect(result.current.error).toBeNull();
  });

  it("shows the error, and reload tries again", async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(503, "down"))
      .mockResolvedValueOnce(["back"]);
    const { result } = renderHook(() => useApiRequest(load));

    await waitFor(() => expect(result.current.error?.message).toBe("down"));
    act(() => result.current.reload());
    expect(result.current.loading).toBe(true);
    expect(result.current.error).toBeNull();
    await waitFor(() => expect(result.current.data).toEqual(["back"]));
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps the old data while a new request loads", async () => {
    let finish;
    const first = vi.fn().mockResolvedValue("page 1");
    const second = vi.fn(() => new Promise((resolve) => (finish = resolve)));
    const { result, rerender } = renderHook(({ load }) => useApiRequest(load), {
      initialProps: { load: first },
    });
    await waitFor(() => expect(result.current.data).toBe("page 1"));

    rerender({ load: second });
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBe("page 1");

    await act(async () => finish("page 2"));
    expect(result.current.data).toBe("page 2");
    expect(result.current.loading).toBe(false);
  });

  it("setData changes the kept result", async () => {
    const load = vi.fn().mockResolvedValue([1]);
    const { result } = renderHook(() => useApiRequest(load));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setData((items) => [...items, 2]));

    expect(result.current.data).toEqual([1, 2]);
  });
});

describe("useSubmit", () => {
  it("returns the result and clears submitting", async () => {
    const { result } = renderHook(() => useSubmit(async (value) => value * 2));

    let outcome;
    await act(async () => {
      outcome = await result.current.submit(21);
    });

    expect(outcome).toEqual({ ok: true, result: 42, error: null });
    expect(result.current.submitting).toBe(false);
  });

  it("keeps the server's error", async () => {
    const { result } = renderHook(() =>
      useSubmit(async () => {
        throw new ApiError(409, "taken");
      }),
    );

    let outcome;
    await act(async () => {
      outcome = await result.current.submit();
    });

    expect(outcome.ok).toBe(false);
    expect(outcome.error.message).toBe("taken");
    expect(result.current.error.message).toBe("taken");
  });

  it("ignores a second submit while the first is running", async () => {
    let finish;
    const action = vi.fn(() => new Promise((resolve) => (finish = resolve)));
    const { result } = renderHook(() => useSubmit(action));

    let first;
    let second;
    await act(async () => {
      first = result.current.submit();
      second = await result.current.submit();
    });
    expect(second.ok).toBe(false);
    expect(action).toHaveBeenCalledTimes(1);

    await act(async () => {
      finish("done");
      await first;
    });
    expect(result.current.submitting).toBe(false);
  });
});
