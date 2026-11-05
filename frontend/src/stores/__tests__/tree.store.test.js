import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import {
  childPath,
  childrenByPath,
  folderSummaries,
  getChildren,
  invalidateDirectory,
  isDirectoryLoaded,
  loadDirectory,
  loadFolderSummary,
  loadTree,
  parentPath,
  refreshDirectories,
  resetTree,
  searchLibrary,
  searchResults,
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

describe("folder summaries", () => {
  /**
   * @param {string} path
   * @param {Record<string, number>} [formatCounts]
   */
  function stubSummary(path, formatCounts = { MP3: 2 }) {
    const url = path
      ? `/api/files/summary?path=${encodeURIComponent(path)}`
      : "/api/files/summary";
    replies.set(
      url,
      jsonResponse({
        path,
        folder_count: 1,
        file_count: 2,
        file_size: 99,
        format_counts: formatCounts,
      }),
    );
    return url;
  }

  it("fetches deep totals once and reuses them", async () => {
    stubSummary("Albums");

    const first = await loadFolderSummary("Albums");
    const second = await loadFolderSummary("Albums");

    expect(first?.file_size).toBe(99);
    expect(second).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(get(folderSummaries).get("Albums")?.format_counts).toEqual({
      MP3: 2,
    });
  });

  it("shares one request between concurrent hovers", async () => {
    stubSummary("Albums");

    await Promise.all([
      loadFolderSummary("Albums"),
      loadFolderSummary("Albums"),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("resolves to null when the request fails", async () => {
    replies.set(
      "/api/files/summary?path=Albums",
      jsonResponse({ error: "nope" }, { status: 500 }),
    );

    await expect(loadFolderSummary("Albums")).resolves.toBeNull();
    expect(get(folderSummaries).has("Albums")).toBe(false);
  });

  it("drops the folder, its subtree and its ancestors after a mutation", async () => {
    const urls = ["", "Albums", "Albums/CD2", "Other"].map((path) =>
      stubSummary(path),
    );
    await Promise.all(
      ["", "Albums", "Albums/CD2", "Other"].map((path) =>
        loadFolderSummary(path),
      ),
    );
    expect(get(folderSummaries).size).toBe(4);

    // A change inside Albums/CD2 moves the size of it, of Albums, and of the
    // library root - but not of an unrelated folder.
    await refreshDirectories(["Albums"]);

    expect([...get(folderSummaries).keys()]).toEqual(["Other"]);
    expect(urls).toHaveLength(4);
  });

  it("forgets everything on reset", async () => {
    stubSummary("Albums");
    await loadFolderSummary("Albums");

    resetTree();

    expect(get(folderSummaries).size).toBe(0);
  });
});

describe("searchLibrary", () => {
  /** @param {string} query @param {Record<string, unknown>[]} results */
  function stubSearch(query, results, truncated = false) {
    replies.set(
      `/api/files/search?q=${encodeURIComponent(query)}`,
      jsonResponse({ query, results, truncated }),
    );
  }

  it("clears the results for an empty query without a request", async () => {
    await searchLibrary("   ");

    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(searchResults)).toEqual({
      query: "",
      results: [],
      truncated: false,
      loading: false,
    });
  });

  it("stores the matches and loads the folders above them", async () => {
    stubSearch("song", [
      {
        name: "song.mp3",
        path: "Albums/CD2/song.mp3",
        type: "file",
        file_type: "audio",
        size: 20,
        parents: ["Albums", "Albums/CD2"],
      },
    ]);
    stubFolder("Albums", []);
    stubFolder("Albums/CD2", []);

    const state = await searchLibrary("song");

    expect(state.results).toHaveLength(1);
    expect(get(searchResults).query).toBe("song");
    expect(isDirectoryLoaded("Albums"));
    expect(isDirectoryLoaded("Albums/CD2"));
  });

  it("reports truncation from the server", async () => {
    stubSearch(
      "a",
      [{ name: "a.mp3", path: "a.mp3", type: "file", parents: [] }],
      true,
    );

    const state = await searchLibrary("a");

    expect(state.truncated).toBe(true);
  });

  it("ignores a stale response after a newer query", async () => {
    /** @type {((value: unknown) => void)[]} */
    const releases = [];
    fetchMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          releases.push(resolve);
        }),
    );

    const first = searchLibrary("old");
    const second = searchLibrary("new");

    // Answer the newer query first, then the stale one.
    releases[1](
      jsonResponse({
        results: [
          { name: "new.mp3", path: "new.mp3", type: "file", parents: [] },
        ],
        truncated: false,
      }),
    );
    releases[0](
      jsonResponse({
        results: [
          { name: "old.mp3", path: "old.mp3", type: "file", parents: [] },
        ],
        truncated: false,
      }),
    );
    await Promise.all([first, second]);

    expect(get(searchResults).query).toBe("new");
    expect(get(searchResults).results.map((hit) => hit.name)).toEqual([
      "new.mp3",
    ]);
  });

  it("keeps an error message instead of throwing", async () => {
    replies.set(
      "/api/files/search?q=boom",
      jsonResponse({ error: "search exploded" }, { status: 500 }),
    );

    const state = await searchLibrary("boom");

    expect(state.results).toEqual([]);
    expect(state.error).toBe("search exploded");
    expect(state.loading).toBe(false);
  });

  it("is cleared by resetTree", async () => {
    stubSearch("song", [
      { name: "song.mp3", path: "song.mp3", type: "file", parents: [] },
    ]);
    await searchLibrary("song");

    resetTree();

    expect(get(searchResults).results).toEqual([]);
  });
});
