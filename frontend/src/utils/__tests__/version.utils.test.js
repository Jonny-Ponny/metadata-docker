import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// version.utils.js keeps the in-flight request in module state, so each test
// imports a fresh copy after resetting the module registry.
async function loadVersionModule() {
  return import("../version.utils.js");
}

describe("fetchVersionInfo", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the version payload with auth headers", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => '{"version":"v1.2.3"}',
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVersionInfo } = await loadVersionModule();
    await expect(fetchVersionInfo()).resolves.toEqual({ version: "v1.2.3" });
    expect(fetchMock).toHaveBeenCalledWith("/api/version", { headers: {} });
  });

  it("shares one request between concurrent callers", async () => {
    /** @type {((value: any) => void) | undefined} */
    let resolveFetch;
    const fetchMock = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVersionInfo } = await loadVersionModule();
    const first = fetchVersionInfo();
    const second = fetchVersionInfo();

    expect(first).toBe(second);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    if (!resolveFetch) throw new Error("fetch was not called");
    resolveFetch({
      ok: true,
      status: 200,
      text: async () => '{"version":"v1"}',
    });

    await expect(first).resolves.toEqual({ version: "v1" });
  });

  it("reuses the resolved payload on later calls", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => '{"version":"v1"}',
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVersionInfo } = await loadVersionModule();
    await fetchVersionInfo();
    await fetchVersionInfo();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("clears the cache after a failure so a retry is possible", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => '{"error":"Unavailable"}',
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        text: async () => '{"version":"v1"}',
      });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchVersionInfo } = await loadVersionModule();
    await expect(fetchVersionInfo()).rejects.toThrow("Unavailable");
    await expect(fetchVersionInfo()).resolves.toEqual({ version: "v1" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("uses the fallback when the failure body is unusable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 502,
        text: async () => "<html>",
      })),
    );

    const { fetchVersionInfo } = await loadVersionModule();
    await expect(fetchVersionInfo()).rejects.toThrow(
      "Could not read the version information (HTTP 502)",
    );
  });
});
