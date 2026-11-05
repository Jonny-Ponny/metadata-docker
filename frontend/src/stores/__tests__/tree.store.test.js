import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import {
  childPath,
  childrenByPath,
  getChildren,
  invalidateDirectory,
  isDirectoryLoaded,
  loadDirectory,
  loadTree,
  parentPath,
  refreshDirectories,
  resetTree,
  tree,
} from "../tree.store.js";

/**
 * @param {Record<string, unknown> | string} body
 * @param {{ status?: number, contentType?: string }} [options]
 */
function jsonResponse(
  body,
  { status = 200, contentType = "application/json" } = {},
) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  };
}

/** @type {Map<string, unknown>} */
let replies;
/** @type {ReturnType<typeof vi.fn>} */
let fetchMock;

beforeEach(() => {
  resetTree();
  replies = new Map();
  fetchMock = vi.fn((/** @type {string} */ url) => {
    const reply = replies.get(url);
    if (reply instanceof Error) return Promise.reject(reply);
    if (reply) return Promise.resolve(reply);
    return Promise.resolve(
      jsonResponse({ error: "not found" }, { status: 404 }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  resetTree();
  vi.unstubAllGlobals();
});

/**
 * @param {string} path
 * @param {unknown[]} [entries]
 */
function stubFolder(path, entries = []) {
  const url = path
    ? `/api/files/dir?path=${encodeURIComponent(path)}`
    : "/api/files/dir";
  replies.set(
    url,
    jsonResponse({
      path,
      entries,
      folder_count: 0,
      file_count: entries.length,
      file_size: 0,
    }),
  );
  return url;
}

describe("path helpers", () => {
  it("joins and splits library paths", () => {
    expect(childPath("", "Albums")).toBe("Albums");
    expect(childPath("Albums", "CD2")).toBe("Albums/CD2");
    expect(parentPath("Albums/CD2")).toBe("Albums");
    expect(parentPath("Albums")).toBe("");
    expect(parentPath("")).toBe("");
  });
});

describe("loadDirectory", () => {
  it("fetches a folder once and caches its children", async () => {
    const url = stubFolder("", [
      { name: "a.mp3", type: "file", path: "a.mp3" },
    ]);

    await loadTree();
    await loadDirectory("");

    expect(isDirectoryLoaded("")).toBe(true);
    expect(getChildren("")).toHaveLength(1);
    expect(get(tree).root).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(url);
  });

  it("shares one request between concurrent expands", async () => {
    stubFolder("Albums", [
      { name: "a.mp3", type: "file", path: "Albums/a.mp3" },
    ]);

    await Promise.all([loadDirectory("Albums"), loadDirectory("Albums")]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("re-fetches only when forced", async () => {
    stubFolder("Albums", []);

    await loadDirectory("Albums");
    await loadDirectory("Albums");
    await loadDirectory("Albums", { force: true });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps already loaded subfolders when its parent refreshes", async () => {
    stubFolder("", [
      { name: "Albums", type: "directory", path: "Albums", has_children: true },
    ]);
    stubFolder("Albums", [
      { name: "a.mp3", type: "file", path: "Albums/a.mp3" },
    ]);
    await loadTree();
    await loadDirectory("Albums");

    await loadDirectory("", { force: true });

    expect(getChildren("Albums")).toHaveLength(1);
  });

  it("reports a failed request without caching an empty folder", async () => {
    const url = stubFolder("Albums");
    replies.set(url, jsonResponse({ error: "nope" }, { status: 500 }));

    await expect(loadDirectory("Albums")).rejects.toThrow("nope");
    expect(isDirectoryLoaded("Albums")).toBe(false);

    // The failed request must not stay in flight, so a retry goes out.
    replies.set(url, jsonResponse({ path: "Albums", entries: [] }));
    await loadDirectory("Albums");
    expect(isDirectoryLoaded("Albums")).toBe(true);
  });

  it("rejects a non-JSON answer", async () => {
    stubFolder("Albums");
    replies.set(
      "/api/files/dir?path=Albums",
      jsonResponse("<html></html>", { contentType: "text/html" }),
    );

    await expect(loadDirectory("Albums")).rejects.toThrow(
      "Expected a JSON response",
    );
  });

  it("ignores a response for a tree that was reset meanwhile", async () => {
    /** @type {(value: unknown) => void} */
    let release = () => {};
    fetchMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );

    const pending = loadDirectory("Albums");
    resetTree();
    release(
      jsonResponse({
        path: "Albums",
        entries: [{ name: "a.mp3", type: "file", path: "Albums/a.mp3" }],
      }),
    );
    await pending;

    expect(isDirectoryLoaded("Albums")).toBe(false);
    expect(get(tree).root).toEqual([]);
  });
});

describe("loadTree", () => {
  it("drops cached folders and reloads the root", async () => {
    stubFolder("", []);
    stubFolder("Albums", [
      { name: "a.mp3", type: "file", path: "Albums/a.mp3" },
    ]);
    await loadTree();
    await loadDirectory("Albums");

    await loadTree();

    expect(isDirectoryLoaded("Albums")).toBe(false);
    expect(isDirectoryLoaded("")).toBe(true);
  });

  it("publishes the error and clears the loading flag", async () => {
    stubFolder("");
    replies.set("/api/files/dir", jsonResponse("down", { status: 500 }));

    await expect(loadTree()).rejects.toThrow();
    expect(get(tree).error).not.toBe("");
    expect(get(tree).loading).toBe(false);
  });
});

describe("refreshDirectories", () => {
  it("reloads loaded folders and skips unknown ones", async () => {
    stubFolder("", []);
    await loadTree();

    await refreshDirectories(["", "Never Opened"]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/files/dir");
  });

  it("deduplicates paths", async () => {
    stubFolder("", []);
    await loadTree();

    await refreshDirectories(["", ""]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("invalidateDirectory", () => {
  it("drops a folder and its subtree", async () => {
    stubFolder("", []);
    stubFolder("Albums", []);
    stubFolder("Albums/CD2", []);
    await loadTree();
    await loadDirectory("Albums");
    await loadDirectory("Albums/CD2");

    invalidateDirectory("Albums");

    expect(isDirectoryLoaded("Albums")).toBe(false);
    expect(isDirectoryLoaded("Albums/CD2")).toBe(false);
    expect(isDirectoryLoaded("")).toBe(true);
    expect([...get(childrenByPath).keys()]).toEqual([""]);
  });
});
