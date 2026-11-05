// src/stores/tree.store.js

// Lazily loaded library tree.
//
// The backend lists one folder per request (`/api/files/dir`), so the app
// only pays for the folders the user actually opens. This store owns the
// per-path cache: children keyed by folder path, one in-flight request per
// path, and invalidation after a mutation.
//
// Paths are library-relative with `/` separators and no leading slash. The
// library root is `""`; a child path is `<parent>/<name>`.

import { get, writable } from "svelte/store";

import { getAuthHeaders } from "./auth.store.js";
import { readApiError } from "../utils/api.utils.js";

/**
 * A folder entry returned by `/api/files/dir`. Directories carry no
 * `children` until the folder is expanded and fetched.
 * @typedef {Object} TreeEntryLike
 * @property {string} name
 * @property {"file" | "directory"} type
 * @property {string} [file_type]
 * @property {string} path
 * @property {number} [size]
 * @property {number} [created]
 * @property {number} [modified]
 * @property {TreeEntryLike[] | undefined} [children]
 * @property {boolean} [has_children]
 * @property {number} [folder_count]
 * @property {number} [file_count]
 * @property {number} [file_size]
 */

/**
 * @typedef {Object} TreeState
 * @property {TreeEntryLike[]} root
 * @property {boolean} loading
 * @property {string} error
 */

/**
 * @typedef {Object} DirectoryResponse
 * @property {string} path
 * @property {TreeEntryLike[]} entries
 * @property {number} folder_count
 * @property {number} file_count
 * @property {number} file_size
 */

/**
 * Deep totals for one folder, as returned by `/api/files/summary`.
 * @typedef {Object} FolderSummaryResponse
 * @property {string} path
 * @property {number} folder_count
 * @property {number} file_count
 * @property {number} file_size
 * @property {Record<string, number>} format_counts
 */

/** @type {TreeState} */
const initialState = {
  root: [],
  loading: false,
  error: "",
};

export const tree = writable(/** @type {TreeState} */ ({ ...initialState }));

// Children by folder path, exposed as a store so a TreeNode re-renders when its
// folder arrives. A missing path means "not fetched yet".
/** @type {import("svelte/store").Writable<Map<string, TreeEntryLike[]>>} */
export const childrenByPath = writable(new Map());

// Latest cache contents, so a request can be answered without reading a store.
/** @type {Map<string, TreeEntryLike[]>} */
let cache = new Map();
// Deep folder totals for the hover tooltip, keyed by folder path. A tooltip
// walks the whole subtree on the server, so results are reused for the session
// and dropped whenever a mutation touches the folder or one of its ancestors.
/** @type {Map<string, FolderSummaryResponse>} */
let summaryCache = new Map();
// Folder tooltips that are being calculated right now.
/** @type {Map<string, Promise<FolderSummaryResponse | null>>} */
let summaryInFlight = new Map();
/** @type {import("svelte/store").Writable<Map<string, FolderSummaryResponse>>} */
export const folderSummaries = writable(new Map());
// One promise per folder so concurrent expands share a request.
/** @type {Map<string, Promise<void>>} */
let inFlight = new Map();
// Bumped on every reset so a late response cannot repopulate a cleared cache.
let generation = 0;

/**
 * Library-wide filename search state. The browser only lists folders the user
 * opened, so a real search runs on the server.
 * @typedef {Object} SearchHit
 * @property {string} name
 * @property {string} path
 * @property {"file" | "directory"} type
 * @property {string} [file_type]
 * @property {number} [size]
 * @property {string[]} parents folder paths above the hit
 */

/**
 * @typedef {Object} SearchState
 * @property {string} query the query the current results belong to
 * @property {SearchHit[]} results
 * @property {boolean} truncated
 * @property {boolean} loading
 * @property {string} [error]
 */

export const searchResults = writable(
  /** @type {SearchState} */ ({
    query: "",
    results: [],
    truncated: false,
    loading: false,
  }),
);

/** In-flight search request, cancelled when the query changes. */
/** @type {AbortController | null} */
let activeSearch = null;

/**
 * Search file and folder names across the whole library.
 *
 * The browser only knows the folders the user opened, so this asks the server.
 * Folders above each hit are loaded afterwards so the match can be shown
 * inside the normal tree.
 *
 * @param {string} query
 * @returns {Promise<SearchState>}
 */
export async function searchLibrary(query) {
  const trimmed = String(query || "").trim();
  if (!trimmed) {
    activeSearch?.abort();
    activeSearch = null;
    searchResults.set({
      query: "",
      results: [],
      truncated: false,
      loading: false,
    });
    return { query: "", results: [], truncated: false, loading: false };
  }

  activeSearch?.abort();
  const controller = new AbortController();
  activeSearch = controller;
  const requestGeneration = generation;

  // Keep the previous results visible while the next query is in flight; the
  // loading flag is what the UI reacts to.
  searchResults.update((state) => ({ ...state, loading: true }));

  try {
    const response = await fetch(
      `/api/files/search?q=${encodeURIComponent(trimmed)}`,
      { headers: getAuthHeaders(), signal: controller.signal },
    );
    if (!response.ok) {
      throw new Error(await readApiError(response, "Search failed"));
    }
    /** @type {{ results: SearchHit[], truncated: boolean }} */
    const body = await response.json();
    if (requestGeneration !== generation || activeSearch !== controller) {
      return get(searchResults);
    }

    const next = {
      query: trimmed,
      results: body.results || [],
      truncated: !!body.truncated,
      loading: false,
    };
    searchResults.set(next);

    // Make the hits renderable in the normal tree: every folder above a hit
    // has to be loaded (and expanded) or the row would have no place to sit.
    const folders = new Set();
    for (const hit of next.results) {
      for (const parent of hit.parents) folders.add(parent);
      if (hit.type === "directory") folders.add(hit.path);
    }
    await Promise.all(
      [...folders].map((path) => loadDirectory(path).catch(() => undefined)),
    );
    return next;
  } catch (error) {
    if (controller.signal.aborted) return get(searchResults);
    searchResults.set({
      query: trimmed,
      results: [],
      truncated: false,
      loading: false,
      error: error instanceof Error ? error.message : String(error),
    });
    return get(searchResults);
  } finally {
    if (activeSearch === controller) activeSearch = null;
  }
}

/**
 * @param {string | null | undefined} parentPath
 * @param {string} name
 * @returns {string}
 */
export function childPath(parentPath, name) {
  const parent = parentPath || "";
  return parent ? `${parent}/${name}` : name;
}

/**
 * @param {string | null | undefined} path
 * @returns {string}
 */
export function parentPath(path) {
  const value = String(path || "");
  const index = value.lastIndexOf("/");
  return index === -1 ? "" : value.slice(0, index);
}

/**
 * @param {string | null | undefined} path
 * @returns {boolean}
 */
export function isDirectoryLoaded(path) {
  return cache.has(path || "");
}

/**
 * Children of a loaded folder, or an empty list while it is not loaded.
 * @param {string | null | undefined} path
 * @returns {TreeEntryLike[]}
 */
export function getChildren(path) {
  return cache.get(path || "") || [];
}

/**
 * Replace the whole cache with the given entries.
 * @param {Map<string, TreeEntryLike[]>} next
 */
function publish(next) {
  cache = next;
  childrenByPath.set(next);
  tree.update((state) => ({ ...state, root: next.get("") || [] }));
}

/**
 * Fetch one folder and store its children. Concurrent calls for the same path
 * share one request; a call after the folder is loaded is a no-op unless
 * `force` is set.
 *
 * @param {string} [path]
 * @param {{ force?: boolean }} [options]
 * @returns {Promise<void>}
 */
export function loadDirectory(path = "", { force = false } = {}) {
  const key = path || "";
  if (!force && cache.has(key)) return Promise.resolve();

  const pending = inFlight.get(key);
  if (pending) return pending;

  const requestGeneration = generation;
  const query = key ? `?path=${encodeURIComponent(key)}` : "";
  const request = fetch(`/api/files/dir${query}`, {
    headers: getAuthHeaders(),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(
          await readApiError(response, "Could not load the folder"),
        );
      }
      const contentType = response.headers?.get?.("content-type");
      // A proxy or a misconfigured reverse proxy can answer the API with an
      // HTML page; parsing it as JSON would report a confusing syntax error.
      if (contentType && !contentType.includes("application/json")) {
        throw new Error(`Expected a JSON response but received ${contentType}`);
      }
      /** @type {DirectoryResponse} */
      const body = await response.json();
      // Ignore a response that belongs to a tree cleared meanwhile (logout, a
      // full refresh).
      if (requestGeneration !== generation) return;

      // Directory entries arrive without children. Reuse the children of a
      // folder that is still cached so a refresh does not collapse it.
      const entries = (body.entries || []).map((entry) => {
        if (entry.type !== "directory") return entry;
        const cached = cache.get(entry.path);
        return {
          ...entry,
          // Reuse the cached children when the folder is still expanded.
          children: cached,
          has_children:
            entry.has_children ?? (cached ? cached.length > 0 : false),
        };
      });

      const next = new Map(cache);
      next.set(key, entries);
      publish(next);
    })
    .finally(() => {
      if (inFlight.get(key) === request) inFlight.delete(key);
    });

  inFlight.set(key, request);
  return request;
}

/**
 * Load the root folder. This drops every cached folder, so a full refresh
 * always starts from the server's view of the library.
 * @returns {Promise<void>}
 */
export async function loadTree() {
  generation += 1;
  inFlight = new Map();
  publish(new Map());
  tree.update((state) => ({ ...state, loading: true, error: "" }));

  try {
    await loadDirectory("", { force: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    tree.update((state) => ({ ...state, error: message }));
    throw error;
  } finally {
    tree.update((state) => ({ ...state, loading: false }));
  }
}

/**
 * Deep totals for a folder tooltip. Results are cached for the session; a
 * concurrent hover reuses the in-flight request, and a failure resolves to
 * `null` so the tooltip can fall back to the direct-child counts.
 *
 * @param {string} [path]
 * @returns {Promise<FolderSummaryResponse | null>}
 */
export function loadFolderSummary(path = "") {
  const key = path || "";
  const cached = summaryCache.get(key);
  if (cached) return Promise.resolve(cached);

  const pending = summaryInFlight.get(key);
  if (pending) return pending;

  const requestGeneration = generation;
  const query = key ? `?path=${encodeURIComponent(key)}` : "";
  const request = fetch(`/api/files/summary${query}`, {
    headers: getAuthHeaders(),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(
          await readApiError(response, "Could not size the folder"),
        );
      }
      /** @type {FolderSummaryResponse} */
      const body = await response.json();
      if (requestGeneration !== generation) return null;
      summaryCache.set(key, body);
      folderSummaries.set(new Map(summaryCache));
      return body;
    })
    .catch(() => null)
    .finally(() => {
      if (summaryInFlight.get(key) === request) summaryInFlight.delete(key);
    });

  summaryInFlight.set(key, request);
  return request;
}

/**
 * Re-fetch folders whose contents a mutation may have changed. Folders that
 * were never loaded are skipped because nothing renders them yet.
 *
 * @param {string[]} [paths]
 * @returns {Promise<void>}
 */
export async function refreshDirectories(paths = []) {
  // A mutation changes the deep total of the folder and of every ancestor, so
  // drop those tooltips instead of serving a stale size.
  for (const path of paths) invalidateSummaries(path);

  /** @type {string[]} */
  const targets = [];
  for (const path of paths) {
    const key = path || "";
    if (!cache.has(key)) continue;
    if (!targets.includes(key)) targets.push(key);
  }
  await Promise.all(
    targets.map((path) => loadDirectory(path, { force: true })),
  );
}

/**
 * Drop the cached deep totals for a folder, its subtree and its ancestors.
 * @param {string} path
 */
function invalidateSummaries(path) {
  const key = path || "";
  /** @type {Map<string, FolderSummaryResponse>} */
  const next = new Map();
  for (const [existing, summary] of summaryCache) {
    // The folder itself and anything below it changed...
    const below =
      existing === key || (key === "" ? true : existing.startsWith(`${key}/`));
    // ...and so did the total of every folder above it.
    const above =
      key !== "" && key.startsWith(existing === "" ? "" : `${existing}/`);
    if (below || above) continue;
    next.set(existing, summary);
  }
  summaryCache = next;
  folderSummaries.set(new Map(summaryCache));
}

/**
 * Drop the children of a folder and its subtree so the next expand fetches
 * them again.
 * @param {string} path
 */
export function invalidateDirectory(path) {
  const key = path || "";
  const prefix = key ? `${key}/` : "";
  /** @type {Map<string, TreeEntryLike[]>} */
  const next = new Map();
  for (const [existing, entries] of cache) {
    if (existing === key || existing.startsWith(prefix)) continue;
    next.set(existing, entries);
  }
  invalidateSummaries(key);
  publish(next);
}

/** Clear everything, for logout. */
export function resetTree() {
  generation += 1;
  inFlight = new Map();
  summaryInFlight = new Map();
  summaryCache = new Map();
  folderSummaries.set(new Map());
  activeSearch?.abort();
  activeSearch = null;
  searchResults.set({
    query: "",
    results: [],
    truncated: false,
    loading: false,
  });
  publish(new Map());
  tree.set({ ...initialState });
}
