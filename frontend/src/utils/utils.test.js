// Unit tests for the small helpers in utils/.
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkCsvFile, MAX_UPLOAD_BYTES } from "./checkCsvFile";
import { cn } from "./cn";
import { initialsOf } from "./initials";
import { reportError } from "./reportError";

function fileOf(name, size) {
  return new File(["x".repeat(size)], name, { type: "text/csv" });
}

describe("initialsOf", () => {
  it.each([
    ["Fake Bikes Ltd", "FB"],
    ["  fake   bikes  ", "FB"],
    ["Warmline", "W"],
    ["Élan Café", "ÉC"],
    ["🚲 Bikes", "🚲B"],
    ["", "?"],
    [null, "?"],
  ])("%j -> %j", (name, expected) => {
    expect(initialsOf(name)).toBe(expected);
  });
});

describe("checkCsvFile", () => {
  it("accepts a normal CSV, any letter case", () => {
    expect(checkCsvFile(fileOf("faq.CSV", 10))).toBeNull();
  });

  it.each([
    [null, "Choose a file."],
    [fileOf("faq.txt", 10), "Choose a .csv file."],
    [fileOf("faq.csv", 0), "The file is empty."],
    [fileOf("faq.csv", MAX_UPLOAD_BYTES + 1), "The file is larger than 1 MB."],
  ])("rejects case %#", (file, message) => {
    expect(checkCsvFile(file)).toBe(message);
  });

  it("accepts a file of exactly 1 MB", () => {
    expect(checkCsvFile(fileOf("faq.csv", MAX_UPLOAD_BYTES))).toBeNull();
  });
});

describe("cn", () => {
  it("lets later Tailwind classes override earlier ones and drops false values", () => {
    const hidden = false;
    expect(cn("p-2 text-sm", hidden && "hidden", "p-4")).toBe("text-sm p-4");
  });
});

describe("reportError", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is the single place errors go (the console, for now)", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const error = new Error("boom");

    reportError(error, { source: "test" });

    expect(log).toHaveBeenCalledWith("[warmline] unexpected error", { source: "test", error });
  });
});
