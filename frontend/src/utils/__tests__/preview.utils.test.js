import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * @param {number} status
 * @param {Blob} blob
 */
function imageResponse(status, blob) {
  return {
    ok: status >= 200 && status < 300,
    status,
    blob: async () => blob,
  };
}

/**
 * @param {number} status
 * @param {number} [size]
 */
function stubImageResponse(status, size = 3) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      imageResponse(
        status,
        new Blob(["x".repeat(size)], { type: "image/png" }),
      ),
    );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * @returns {{ createObjectURL: ReturnType<typeof vi.fn>, revokeObjectURL: ReturnType<typeof vi.fn> }}
 */
function stubObjectUrls() {
  let counter = 0;
  const createObjectURL = vi.fn(
    (/** @type {Blob} */ _blob) => `blob:preview-${++counter}`,
  );
  const revokeObjectURL = vi.fn();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectURL,
  });
  return { createObjectURL, revokeObjectURL };
}

describe("preview utils", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (/** @type {any} */ (URL).createObjectURL);
    delete (/** @type {any} */ (URL).revokeObjectURL);
  });

  it("detects remote image URLs", async () => {
    const { isRemoteImageUrl } = await import("../preview.utils.js");

    expect(isRemoteImageUrl("https://example.com/a.jpg")).toBe(true);
    expect(isRemoteImageUrl("HTTP://example.com/a.jpg")).toBe(true);
    expect(isRemoteImageUrl("data:image/png;base64,AAAA")).toBe(false);
    expect(isRemoteImageUrl("blob:preview-1")).toBe(false);
    expect(isRemoteImageUrl("ftp://example.com/a.jpg")).toBe(false);
    expect(isRemoteImageUrl(null)).toBe(false);
    expect(isRemoteImageUrl(42)).toBe(false);
  });

  it("returns local URLs unchanged without fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { loadPreviewImage } = await import("../preview.utils.js");

    await expect(loadPreviewImage("data:image/png;base64,AAAA")).resolves.toBe(
      "data:image/png;base64,AAAA",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies remote images through the preview endpoint", async () => {
    const fetchMock = stubImageResponse(200);
    const { createObjectURL } = stubObjectUrls();
    const { loadPreviewImage } = await import("../preview.utils.js");
    const { authToken } = await import("../../stores/auth.store.js");
    authToken.set("token-1");

    const result = await loadPreviewImage("https://example.com/a b.jpg");

    expect(result).toBe("blob:preview-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/metadata/picture/preview?url=https%3A%2F%2Fexample.com%2Fa%20b.jpg",
      { headers: { Authorization: "Bearer token-1" } },
    );
    expect(createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("caches a resolved preview", async () => {
    const fetchMock = stubImageResponse(200);
    stubObjectUrls();
    const { loadPreviewImage } = await import("../preview.utils.js");

    const first = await loadPreviewImage("https://example.com/a.jpg");
    const second = await loadPreviewImage("https://example.com/a.jpg");

    expect(second).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("deduplicates concurrent requests", async () => {
    /** @type {(value: unknown) => void} */
    let resolveFetch = () => {};
    const fetchMock = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    stubObjectUrls();
    const { loadPreviewImage } = await import("../preview.utils.js");

    const first = loadPreviewImage("https://example.com/a.jpg");
    const second = loadPreviewImage("https://example.com/a.jpg");
    resolveFetch(imageResponse(200, new Blob(["img"], { type: "image/jpeg" })));

    await expect(Promise.all([first, second])).resolves.toEqual([
      "blob:preview-1",
      "blob:preview-1",
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects a non-image payload and allows a retry", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        imageResponse(200, new Blob(["html"], { type: "text/html" })),
      )
      .mockResolvedValueOnce(
        imageResponse(200, new Blob(["img"], { type: "image/png" })),
      );
    vi.stubGlobal("fetch", fetchMock);
    stubObjectUrls();
    const { loadPreviewImage } = await import("../preview.utils.js");

    await expect(loadPreviewImage("https://example.com/a.jpg")).rejects.toThrow(
      "Cover preview was not an image",
    );

    await expect(loadPreviewImage("https://example.com/a.jpg")).resolves.toBe(
      "blob:preview-1",
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("reports the HTTP status of a failed preview", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(imageResponse(502, new Blob([]))),
    );
    const { loadPreviewImage } = await import("../preview.utils.js");

    await expect(loadPreviewImage("https://example.com/a.jpg")).rejects.toThrow(
      "Cover preview failed (502)",
    );
  });

  it("evicts the oldest preview after forty entries", async () => {
    stubImageResponse(200);
    const { revokeObjectURL } = stubObjectUrls();
    const { loadPreviewImage } = await import("../preview.utils.js");

    for (let index = 0; index < 41; index++) {
      await loadPreviewImage(`https://example.com/${index}.jpg`);
    }

    expect(revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:preview-1");
  });
});
