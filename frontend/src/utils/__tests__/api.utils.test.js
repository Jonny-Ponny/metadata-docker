import { describe, expect, it, vi } from "vitest";
import {
  formatApiErrorMessage,
  messageFromBody,
  readApiError,
  readJsonResponse,
} from "../api.utils.js";

describe("messageFromBody", () => {
  it("reads an error string from JSON", () => {
    expect(messageFromBody('{"error":"Invalid new name"}')).toBe(
      "Invalid new name",
    );
    expect(messageFromBody('{"message":"Something failed"}')).toBe(
      "Something failed",
    );
  });

  it("reads a nested message object", () => {
    expect(messageFromBody('{"error":{"message":"Nested failure"}}')).toBe(
      "Nested failure",
    );
  });

  it("prefers error over message", () => {
    expect(messageFromBody('{"error":"First","message":"Second"}')).toBe(
      "First",
    );
  });

  it("ignores empty and non-string JSON values", () => {
    expect(messageFromBody('{"error":"   "}')).toBe("");
    expect(messageFromBody('{"error":42}')).toBe("");
    expect(messageFromBody('{"error":{}}')).toBe("");
  });

  it("ignores malformed JSON and HTML bodies", () => {
    expect(messageFromBody('{"error":')).toBe("");
    expect(messageFromBody("<html>Bad gateway</html>")).toBe("");
    expect(messageFromBody("   ")).toBe("");
    expect(messageFromBody(undefined)).toBe("");
  });

  it("returns short plain text", () => {
    expect(messageFromBody("  Plain failure  ")).toBe("Plain failure");
  });

  it("ignores oversized plain text", () => {
    expect(messageFromBody("x".repeat(201))).toBe("");
  });
});

describe("formatApiErrorMessage", () => {
  it("prefers the parsed body message", () => {
    expect(formatApiErrorMessage('{"error":"Bad"}', "Upload failed", 400)).toBe(
      "Bad",
    );
  });

  it("appends the status to the fallback", () => {
    expect(formatApiErrorMessage("", "Upload failed", 503)).toBe(
      "Upload failed (HTTP 503)",
    );
    expect(formatApiErrorMessage("", "Upload failed")).toBe("Upload failed");
  });
});

describe("readApiError", () => {
  const response = (body, status = 400, throws = false) => ({
    status,
    text: async () => {
      if (throws) throw new Error("stream failed");
      return body;
    },
  });

  it("reads the body once and returns the backend message", async () => {
    const text = vi.fn(async () => '{"error":"Nope"}');
    const result = await readApiError({ status: 400, text }, "Fallback");

    expect(result).toBe("Nope");
    expect(text).toHaveBeenCalledTimes(1);
  });

  it("falls back with the status for unusable bodies", async () => {
    await expect(readApiError(response("<html>"), "Fallback")).resolves.toBe(
      "Fallback (HTTP 400)",
    );
  });

  it("falls back when the body cannot be read", async () => {
    await expect(
      readApiError(response("", 500, true), "Fallback"),
    ).resolves.toBe("Fallback (HTTP 500)");
  });
});

describe("readJsonResponse", () => {
  it("parses JSON", async () => {
    const result = await readJsonResponse({
      status: 200,
      text: async () => '{"ok":true}',
    });

    expect(result).toEqual({ ok: true });
  });

  it("returns an empty object for an empty body", async () => {
    await expect(
      readJsonResponse({ status: 204, text: async () => "" }),
    ).resolves.toEqual({});
  });

  it("throws with the status for malformed JSON", async () => {
    await expect(
      readJsonResponse(
        { status: 502, text: async () => "<html>" },
        "Bad response",
      ),
    ).rejects.toThrow("Bad response (HTTP 502)");
  });
});
