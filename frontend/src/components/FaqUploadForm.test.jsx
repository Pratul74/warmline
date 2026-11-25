import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_UPLOAD_BYTES } from "../api/faq.js";
import FaqUploadForm from "./FaqUploadForm.jsx";

// fetch is replaced by a fake for every test: no backend, no network.
function reply(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function csv(name = "faq.csv", text = "question,answer\nHours?,9 to 6\n") {
  return new File([text], name, { type: "text/csv" });
}

function setup() {
  const onUploaded = vi.fn();
  // applyAccept: false lets the test "pick" files the accept attribute would hide,
  // the way a user can with "All files" in the file dialog.
  const user = userEvent.setup({ applyAccept: false });
  render(<FaqUploadForm token="fake-token" onUploaded={onUploaded} />);
  const input = screen.getByLabelText(/CSV file/);
  const button = screen.getByRole("button", { name: "Upload" });
  return { user, input, button, onUploaded };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FaqUploadForm", () => {
  it("blocks a file that is not .csv, without calling the server", async () => {
    const { user, input, button } = setup();

    await user.upload(input, csv("faq.txt"));

    expect(screen.getByRole("alert")).toHaveProperty("textContent", "Choose a .csv file.");
    expect(button.disabled).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("blocks a file over 1 MB, without calling the server", async () => {
    const { user, input, button } = setup();

    await user.upload(input, csv("big.csv", "x".repeat(MAX_UPLOAD_BYTES + 1)));

    expect(screen.getByRole("alert").textContent).toBe("The file is larger than 1 MB.");
    expect(button.disabled).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends the file as multipart with the owner token and shows the counts", async () => {
    fetch.mockResolvedValue(reply(200, { inserted: 3, updated: 1, unchanged: 2 }));
    const { user, input, button, onUploaded } = setup();
    const file = csv();

    await user.upload(input, file);
    await user.click(button);

    expect(await screen.findByRole("status")).toHaveProperty(
      "textContent",
      "Upload saved. 3 added, 1 updated, 2 unchanged.",
    );
    expect(onUploaded).toHaveBeenCalledWith({ inserted: 3, updated: 1, unchanged: 2 });

    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("http://localhost:8000/faq/upload");
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer fake-token");
    // No Content-Type: the browser must set multipart/form-data with its boundary.
    expect(options.headers["Content-Type"]).toBeUndefined();
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get("file").name).toBe("faq.csv");
  });

  it("shows the server's 422 message and every row error exactly as sent", async () => {
    fetch.mockResolvedValue(
      reply(422, {
        detail: "2 problem(s) found. Nothing was saved; fix the rows and upload again.",
        errors: [
          { row: 3, field: "answer", message: "must not be empty" },
          { row: 7, field: "question", message: "same question as row 2" },
        ],
      }),
    );
    const { user, input, button, onUploaded } = setup();

    await user.upload(input, csv());
    await user.click(button);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/^2 problem\(s\) found/)).toBeTruthy();
    const rows = within(alert)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
    expect(rows).toEqual([
      ["3", "answer", "must not be empty"],
      ["7", "question", "same question as row 2"],
    ]);
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("shows a file-level server error without a table", async () => {
    fetch.mockResolvedValue(reply(413, { detail: "The upload is larger than 1 MB." }));
    const { user, input, button } = setup();

    await user.upload(input, csv());
    await user.click(button);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("The upload is larger than 1 MB.");
    expect(within(alert).queryByRole("table")).toBeNull();
  });

  it("disables the button and says Uploading… while the request runs", async () => {
    let finish;
    fetch.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { user, input, button } = setup();

    await user.upload(input, csv());
    await user.click(button);

    expect(button.textContent).toBe("Uploading…");
    expect(button.disabled).toBe(true);

    finish(reply(200, { inserted: 1, updated: 0, unchanged: 0 }));
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(button.textContent).toBe("Upload");
  });

  it("shows a clear message when the server cannot be reached", async () => {
    fetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const { user, input, button } = setup();

    await user.upload(input, csv());
    await user.click(button);

    expect((await screen.findByRole("alert")).textContent).toMatch(/Can't reach the server/);
  });
});
