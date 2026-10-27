// src/utils/upload.utils.js

// Upload helpers shared by the upload store and the tray component.
//
// Uploads are one multipart request per file. XMLHttpRequest is used instead
// of fetch because only XHR exposes upload progress events; see
// uploadWithProgress. Everything here is browser-only.

import { getAuthHeaders } from "../stores/auth.store.js";
import { formatApiErrorMessage } from "./api.utils.js";
import { fetchVersionInfo } from "./version.utils.js";

// Chromium allows ~6 connections per origin over HTTP/1.1 and the container
// runs gunicorn with 8 threads, so 4 leaves room for tree reloads and metadata
// requests while the upload is running.
export const UPLOAD_CONCURRENCY = 4;

// Keep this in sync with UPLOAD_CONFLICT_* in backend/app.py.
export const UPLOAD_CONFLICT_SKIP_IDENTICAL = "skip-identical";
export const UPLOAD_CONFLICT_KEEP_BOTH = "keep-both";

// Temp files below this size are not spooled to /tmp by Werkzeug.
const SPOOL_THRESHOLD_BYTES = 512 * 1024;

const JUNK_FILE_PATTERNS = [
  /^\.DS_Store$/i,
  /^\._/, // AppleDouble resource forks
  /^Thumbs\.db$/i,
  /^desktop\.ini$/i,
  /^\.Trashes$/i,
];

const JUNK_DIR_NAMES = new Set([
  "__MACOSX",
  "@eaDir",
  ".Trashes",
  ".Spotlight-V100",
  ".fseventsd",
]);

/**
 * A dropped file plus its path relative to the drop root.
 * @typedef {Object} DroppedFile
 * @property {File} file
 * @property {string} relativePath
 */

/**
 * @typedef {Object} ScanProgress
 * @property {number} files
 * @property {number} bytes
 */

/**
 * @typedef {Object} CollectDropOptions
 * @property {AbortSignal} [signal]
 * @property {(progress: ScanProgress) => void} [onProgress]
 */

/**
 * @typedef {Object} ScanContext
 * @property {AbortSignal} [signal]
 * @property {DroppedFile[]} collected
 * @property {number} count
 * @property {number} bytes
 * @property {(count: number, bytes: number) => void} report
 */

/**
 * @typedef {Object} UploadOptions
 * @property {string} [targetPath]
 * @property {string} [conflict]
 * @property {(loaded: number, total: number) => void} [onProgress]
 * @property {AbortSignal} [signal]
 */

/**
 * @typedef {Error & { status?: number, retryable?: boolean, aborted?: boolean }} UploadError
 */

/**
 * File/folder node fields the existing-file index reads.
 * @typedef {Object} TreeNode
 * @property {string} type
 * @property {string} path
 * @property {number} [size]
 * @property {TreeNode[]} [children]
 */

/**
 * @typedef {Object} StorageInfo
 * @property {number} [headroom]
 * @property {{ free?: number }} [music]
 * @property {{ free?: number }} [temp]
 */

/**
 * True for OS metadata files that are never wanted in a music library.
 * @param {string | null} [relativePath]
 * @returns {boolean}
 */
export function isJunkPath(relativePath) {
  const segments = String(relativePath || "")
    .split("/")
    .filter(Boolean);
  return segments.some((segment, index) => {
    const isLast = index === segments.length - 1;
    if (JUNK_DIR_NAMES.has(segment)) return true;
    return (
      isLast && JUNK_FILE_PATTERNS.some((pattern) => pattern.test(segment))
    );
  });
}

/**
 * Turn a drop into a flat list of `{ file, relativePath }`.
 *
 * Prefer the FileList: Chrome populates `webkitRelativePath` for the folder
 * picker with the complete recursive list, so sizes (and therefore the exact
 * total byte count) are available without walking the tree. A folder dropped
 * from the file manager usually arrives as directory entries instead, so the
 * fallback walk has to resolve every file handle itself.
 *
 * `signal` makes the walk cancellable (the scan of a large folder is the
 * slowest part before the first byte is sent) and `onProgress` reports how
 * many files / bytes have been found so far, for the tray.
 *
 * @param {FileSystemEntry[]} [entries]
 * @param {File[]} [files]
 * @param {CollectDropOptions} [options]
 * @returns {Promise<DroppedFile[]>}
 */
export async function collectDropFiles(
  entries = [],
  files = [],
  { signal, onProgress } = {},
) {
  throwIfAborted(signal);

  const fileList = Array.from(files || []);
  /**
   * @param {number} count
   * @param {number} bytes
   */
  const report = (count, bytes) => onProgress?.({ files: count, bytes });

  if (fileList.some((file) => file.webkitRelativePath)) {
    const collected = fileList
      .map((file) => ({
        file,
        relativePath: file.webkitRelativePath || file.name,
      }))
      .filter((entry) => !isJunkPath(entry.relativePath));
    report(
      collected.length,
      collected.reduce((sum, entry) => sum + entry.file.size, 0),
    );
    return collected;
  }

  const topLevelEntries = Array.from(entries || []).filter(Boolean);
  if (topLevelEntries.some((entry) => entry.isDirectory)) {
    /** @type {ScanContext} */
    const context = {
      signal,
      collected: [],
      count: 0,
      bytes: 0,
      report,
    };
    await Promise.all(
      topLevelEntries.map((entry) => walkEntry(entry, "", context)),
    );
    return context.collected;
  }

  const collected = fileList
    .map((file) => ({ file, relativePath: file.name }))
    .filter((entry) => !isJunkPath(entry.relativePath));
  report(
    collected.length,
    collected.reduce((sum, entry) => sum + entry.file.size, 0),
  );
  return collected;
}

// `entry.file()` is asynchronous and was previously awaited one file at a
// time, which made importing a folder with thousands of small tracks take a
// long time. Resolve a directory batch concurrently instead; 32 keeps the
// browser's filesystem queue busy without opening thousands of handles.
const SCAN_CONCURRENCY = 32;

/**
 * @param {AbortSignal} [signal]
 */
function throwIfAborted(signal) {
  if (!signal?.aborted) return;
  const error = new Error("Upload cancelled.");
  error.name = "AbortError";
  throw error;
}

/**
 * @param {FileSystemFileEntry} entry
 * @returns {Promise<File>}
 */
function readFileEntry(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

/**
 * @param {FileSystemDirectoryReader} reader
 * @returns {Promise<FileSystemEntry[]>}
 */
function readEntryBatch(reader) {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

/**
 * @param {FileSystemEntry} entry
 * @param {string} parentPath
 * @param {ScanContext} context
 */
async function walkEntry(entry, parentPath, context) {
  throwIfAborted(context.signal);

  const relativePath = parentPath ? `${parentPath}/${entry.name}` : entry.name;

  if (entry.isFile) {
    if (isJunkPath(relativePath)) return;
    const file = await readFileEntry(
      /** @type {FileSystemFileEntry} */ (entry),
    );
    throwIfAborted(context.signal);
    context.collected.push({ file, relativePath });
    context.count += 1;
    context.bytes += file.size;
    context.report(context.count, context.bytes);
    return;
  }

  if (!entry.isDirectory) return;
  if (JUNK_DIR_NAMES.has(entry.name) || isJunkPath(relativePath)) return;

  const reader = /** @type {FileSystemDirectoryEntry} */ (entry).createReader();
  // readEntries() returns at most 100 entries per call, so drain it instead of
  // assuming a single call sees the whole directory.
  while (true) {
    throwIfAborted(context.signal);
    const batch = await readEntryBatch(reader);
    if (!batch.length) break;
    await mapLimit(batch, SCAN_CONCURRENCY, (child) =>
      walkEntry(child, relativePath, context),
    );
  }
}

/**
 * @template T
 * @param {T[]} items
 * @param {number} limit
 * @param {(item: T) => Promise<void>} run
 * @returns {Promise<void>}
 */
async function mapLimit(items, limit, run) {
  let next = 0;
  const workers = Array.from(
    { length: Math.min(limit, items.length) },
    async () => {
      while (next < items.length) {
        const index = next;
        next += 1;
        // Needed so a rejected entry stops the others instead of rejecting an
        // unhandled sibling promise.

        await run(items[index]);
      }
    },
  );
  await Promise.all(workers);
}

/**
 * Map relative library path -> file size, from the already loaded tree.
 * @param {TreeNode[]} [nodes]
 * @param {Map<string, number | undefined>} [index]
 * @returns {Map<string, number | undefined>}
 */
export function buildExistingIndex(nodes, index = new Map()) {
  for (const node of nodes || []) {
    if (!node) continue;
    if (node.type === "file") {
      index.set(node.path, node.size);
    } else if (node.children) {
      buildExistingIndex(node.children, index);
    }
  }
  return index;
}

/**
 * @param {...(string | null | undefined)} parts
 * @returns {string}
 */
export function joinUploadPath(...parts) {
  return parts
    .filter((part) => part !== undefined && part !== null && part !== "")
    .join("/");
}

/**
 * @param {string | null} [relativePath]
 * @returns {string}
 */
export function dirnameUploadPath(relativePath) {
  const parts = String(relativePath || "").split("/");
  parts.pop();
  return parts.join("/");
}

/**
 * Create a folder, merging into it when it already exists.
 * @param {string} relativePath
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<string>}
 */
export async function ensureDirectory(relativePath, { signal } = {}) {
  const response = await fetch("/api/mkdir", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ path: relativePath, conflict: "merge" }),
    signal,
  });

  const text = await response.text();
  /** @type {Record<string, any>} */
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = {};
    }
  }

  if (!response.ok) {
    throw new Error(
      formatApiErrorMessage(
        text,
        "Could not create the destination folder",
        response.status,
      ),
    );
  }

  return data.path ?? relativePath;
}

/**
 * @param {Response} response
 * @param {string} fallback
 * @returns {Promise<Record<string, any>>}
 */
async function readJsonBody(response, fallback) {
  const text = await response.text();
  /** @type {Record<string, any>} */
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = {};
    }
  }
  if (!response.ok) {
    throw new Error(formatApiErrorMessage(text, fallback, response.status));
  }
  return data;
}

/** Free space in the library and in the temp directory used for spooling. */
export async function fetchStorage() {
  const response = await fetch("/api/storage", { headers: getAuthHeaders() });
  return readJsonBody(response, "Could not check free disk space");
}

/** Per-request upload limit (MAX_UPLOAD_MB), exposed by /api/version. */
export async function fetchUploadLimit() {
  const data = await fetchVersionInfo();
  return Number(data.max_upload_bytes) || 0;
}

/**
 * Upload a single file and report bytes as they are sent.
 *
 * Resolves with the parsed JSON response. Rejections carry `status`,
 * `retryable` and `aborted` so the queue can decide between retrying,
 * reporting and stopping.
 *
 * @param {File} file
 * @param {UploadOptions} [options]
 * @returns {Promise<any>}
 */
export function uploadWithProgress(
  file,
  {
    targetPath = "",
    conflict = UPLOAD_CONFLICT_SKIP_IDENTICAL,
    onProgress,
    signal,
  } = {},
) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");

    // The global fetch wrapper in App.svelte does not apply to XHR, so the
    // session header has to be set explicitly.
    for (const [name, value] of Object.entries(getAuthHeaders())) {
      xhr.setRequestHeader(name, value);
    }

    /**
     * @param {string} message
     * @param {number} status
     * @param {Partial<UploadError>} [extra]
     */
    const fail = (message, status, extra = {}) => {
      const error = /** @type {UploadError} */ (new Error(message));
      error.status = status;
      error.retryable =
        status === 0 || status === 408 || status === 429 || status >= 500;
      Object.assign(error, extra);
      reject(error);
    };

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded, event.total);
    };

    xhr.onload = () => {
      /** @type {any} */
      let data = {};
      if (xhr.responseText) {
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          data = {};
        }
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(file.size, file.size);
        resolve(data);
        return;
      }

      fail(
        formatApiErrorMessage(xhr.responseText, "Upload failed", xhr.status),
        xhr.status,
      );
    };

    xhr.onerror = () =>
      fail("Network error while uploading. Is the server reachable?", 0);
    xhr.ontimeout = () => fail("The upload timed out.", 0);
    xhr.onabort = () => fail("Upload cancelled.", 0, { aborted: true });

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    const form = new FormData();
    form.append("file", file);
    form.append("targetPath", targetPath || "");
    form.append("originalFilename", file.name);
    form.append("conflict", conflict);

    xhr.send(form);
  });
}

/**
 * Check the preflight conditions for a batch of files.
 * @param {StorageInfo | undefined} storage
 * @param {number} totalBytes
 * @param {number} tempPeakBytes
 * @returns {{ target: string, needed: number, free: number, message: string }[]}
 */
export function checkSpace(storage, totalBytes, tempPeakBytes) {
  const problems = [];
  const headroom = Number(storage?.headroom) || 0;
  const musicFree = Number(storage?.music?.free) || 0;
  const tempFree = Number(storage?.temp?.free) || 0;

  // Small uploads should not be blocked by the headroom, only by real lack of
  // space; large ones leave a margin so the copy has room to finish.
  const musicNeeded = totalBytes + Math.min(totalBytes * 0.02, headroom);
  if (musicNeeded > musicFree) {
    problems.push({
      target: "library",
      needed: totalBytes,
      free: musicFree,
      message:
        `Not enough space in the music library: ` +
        `need ${formatBytes(totalBytes)}, ${formatBytes(musicFree)} free.`,
    });
  }

  // Werkzeug spools each request body over ~500 KB to the temp directory
  // before it is copied into the library. The peak is the bytes of the files
  // being uploaded at the same time, not one file times the concurrency.
  if (tempPeakBytes > SPOOL_THRESHOLD_BYTES) {
    const tempNeeded = tempPeakBytes * 1.1;
    if (tempNeeded > tempFree) {
      problems.push({
        target: "temp",
        needed: tempNeeded,
        free: tempFree,
        message:
          `Not enough temporary space for uploads: ` +
          `need about ${formatBytes(tempNeeded)}, ${formatBytes(tempFree)} free.`,
      });
    }
  }

  return problems;
}

/**
 * @param {unknown} bytes
 * @returns {string}
 */
export function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 100 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

/**
 * @param {number | undefined} seconds
 * @returns {string}
 */
export function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0)
    return "";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
