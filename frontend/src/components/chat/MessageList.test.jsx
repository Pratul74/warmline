// Component tests for the chat message list: plain-text rendering, failed messages, typing.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MessageList } from "./MessageList";

afterEach(cleanup);

const AT = Date.UTC(2026, 10, 25, 9, 30);

function renderList(props = {}) {
  const onRetry = vi.fn();
  render(
    <MessageList greeting="Hi there!" messages={[]} sending={false} onRetry={onRetry} {...props} />,
  );
  return { onRetry, log: screen.getByRole("log") };
}

describe("MessageList", () => {
  it("shows the greeting first, then the messages in order", () => {
    const { log } = renderList({
      messages: [
        { id: 1, role: "user", text: "Are you open on Sunday?", at: AT, failed: false },
        { id: 2, role: "assistant", text: "Yes, 10 to 4.", at: AT, failed: false },
      ],
    });

    const items = within(log)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(items[0]).toContain("Hi there!");
    expect(items[1]).toContain("You said:Are you open on Sunday?");
    expect(items[2]).toContain("Assistant said:Yes, 10 to 4.");
  });

  it("renders HTML in a message as text, so it cannot run", () => {
    const attack = '<img src=x onerror="alert(1)"> hello';
    const { log } = renderList({
      messages: [{ id: 1, role: "assistant", text: attack, at: AT, failed: false }],
    });

    expect(log.querySelector("img")).toBeNull();
    expect(within(log).getByText(attack)).toBeTruthy();
  });

  it("marks a failed message and calls onRetry with its id", async () => {
    const { onRetry, log } = renderList({
      messages: [{ id: 7, role: "user", text: "Book me in", at: AT, failed: true }],
    });

    expect(within(log).getByText("Not sent")).toBeTruthy();
    await userEvent.click(within(log).getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledWith(7);
  });

  it("disables Retry while sending is blocked", () => {
    const { log } = renderList({
      messages: [{ id: 7, role: "user", text: "Book me in", at: AT, failed: true }],
      retryDisabled: true,
    });

    expect(within(log).getByRole("button", { name: "Retry" }).disabled).toBe(true);
  });

  it("shows the typing indicator only while sending", () => {
    renderList({ sending: true });
    expect(screen.getByText("Assistant is typing…")).toBeTruthy();
    cleanup();

    renderList({ sending: false });
    expect(screen.queryByText("Assistant is typing…")).toBeNull();
  });
});
