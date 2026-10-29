import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * @param {number} status
 * @param {Record<string, unknown> | string} body
 */
function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => (typeof body === "string" ? JSON.parse(body) : body),
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  };
}

describe("cover utils", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("applies a URL to the current file", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response(200, { success: true, picture: "data:," }));
    vi.stubGlobal("fetch", fetchMock);

    const { setCoverFromUrl } = await import("../cover.utils.js");
    const result = await setCoverFromUrl(
      "folder/song.mp3",
      "https://example.com/cover.jpg",
    );

    expect(result).toEqual({ success: true, picture: "data:," });
    expect(fetchMock).toHaveBeenCalledWith("/api/metadata/picture/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: "folder/song.mp3",
        url: "https://example.com/cover.jpg",
      }),
    });
  });

  it("uses the current-folder endpoint by default", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response(200, { success: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { setCoverFromUrl } = await import("../cover.utils.js");
    await setCoverFromUrl("folder", "https://example.com/cover.jpg", {
      toFolder: true,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/metadata/picture/url/folder/current",
    );
  });

  it("uses the recursive folder endpoint when asked", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response(200, { success: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { setCoverFromUrl } = await import("../cover.utils.js");
    await setCoverFromUrl("folder", "https://example.com/cover.jpg", {
      toFolder: true,
      recursive: true,
    });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/metadata/picture/url/folder");
  });

  it("throws the backend error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response(400, { error: "URL is not public" })),
    );

    const { setCoverFromUrl } = await import("../cover.utils.js");

    await expect(
      setCoverFromUrl("folder/song.mp3", "http://127.0.0.1/secret"),
    ).rejects.toThrow("URL is not public");
  });
});
