// Tests for the hosted chat page against a fake fetch: the whole conversation flow, the
// conversation token, a failed message with Retry, the 429 countdown and a link closed mid-chat.
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "./ChatPage";

const PROFILE = {
  name: "Website chat",
  greeting: "Welcome to Fake Bikes!",
  business_name: "Fake Bikes",
};

function reply(status, body, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers });
}

async function openChat() {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <MemoryRouter initialEntries={["/c/abc123"]}>
      <Routes>
        <Route path="/c/:publicId" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText("Welcome to Fake Bikes!");
  return user;
}

async function say(user, text) {
  await user.type(screen.getByRole("textbox", { name: "Message" }), text);
  await user.keyboard("{Enter}");
}

function sentBodies() {
  return fetch.mock.calls
    .filter(([, options]) => options.method === "POST")
    .map(([, options]) => JSON.parse(options.body));
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("fetch", vi.fn());
  fetch.mockResolvedValueOnce(reply(200, PROFILE));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ChatPage", () => {
  it("sends messages and passes the conversation token back on the next one", async () => {
    fetch
      .mockResolvedValueOnce(reply(200, { conversation_token: "tok-1", reply: "We open at 9." }))
      .mockResolvedValueOnce(reply(200, { conversation_token: "tok-1", reply: "Until 6." }));
    const user = await openChat();

    expect(screen.getByRole("heading", { name: "Fake Bikes" })).toBeTruthy();
    await say(user, "When do you open?");
    await screen.findByText("We open at 9.");
    await say(user, "And close?");
    await screen.findByText("Until 6.");

    expect(sentBodies()).toEqual([
      { message: "When do you open?", conversation_token: null },
      { message: "And close?", conversation_token: "tok-1" },
    ]);
    expect(fetch.mock.calls[1][0]).toBe("http://localhost:8000/public/c/abc123/messages");
  });

  it("keeps a failed message with Retry, and Retry sends it again", async () => {
    fetch
      .mockResolvedValueOnce(reply(503, { detail: "The assistant is busy, please try again." }))
      .mockResolvedValueOnce(reply(200, { conversation_token: "tok-1", reply: "Booked!" }));
    const user = await openChat();

    await say(user, "Book me in");
    expect((await screen.findByRole("alert")).textContent).toContain("The assistant is busy");
    expect(screen.getByText("Not sent")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("Booked!");
    expect(screen.queryByText("Not sent")).toBeNull();
    expect(sentBodies().map((body) => body.message)).toEqual(["Book me in", "Book me in"]);
  });

  it("counts down after a 429 and blocks sending until it ends", async () => {
    fetch.mockResolvedValueOnce(
      reply(429, { detail: "Too many requests" }, { "Retry-After": "3" }),
    );
    const user = await openChat();

    await say(user, "Hello");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("You can send again in 3s.");
    expect(screen.getByRole("button", { name: "Retry" }).disabled).toBe(true);

    // One second at a time: each tick schedules the next one after React re-renders.
    for (const left of [2, 1]) {
      await act(async () => vi.advanceTimersByTime(1000));
      expect(screen.getByRole("alert").textContent).toContain(`You can send again in ${left}s.`);
    }
    await act(async () => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("alert").textContent).not.toContain("You can send again");
    expect(screen.getByRole("button", { name: "Retry" }).disabled).toBe(false);
  });

  it("closes the chat when the link is disabled mid-conversation", async () => {
    fetch.mockResolvedValueOnce(reply(403, { detail: "This chat is unavailable." }));
    const user = await openChat();

    await say(user, "Hello");

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("This chat is currently unavailable")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Message" })).toBeNull();
  });

  it("shows a friendly page for an unknown link", async () => {
    fetch.mockReset();
    fetch.mockResolvedValueOnce(reply(404, { detail: "Not found" }));
    render(
      <MemoryRouter initialEntries={["/c/missing"]}>
        <Routes>
          <Route path="/c/:publicId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "This chat link doesn't exist" }),
    ).toBeTruthy();
  });
});
