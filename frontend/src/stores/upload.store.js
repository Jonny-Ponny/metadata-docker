// src/stores/upload.store.js

// Upload queue for drag-and-drop and the folder picker.
//
// One multipart request per file, at most UPLOAD_CONCURRENCY at a time. The
// store owns byte accounting (per-byte progress instead of a file count),
// cancellation, retries, the free-space preflight and the conflict policy.
// It deliberately keeps no state on the server, so a cancelled or closed tab
// never leaves a half-written file: the backend writes to a temp file and
// renames it into place.

import { get, writable } from "svelte/store";

import { logout } from "./auth.store.js";
import { toast } from "./toast.store.js";
import {
  UPLOAD_CONCURRENCY,
  UPLOAD_CONFLICT_SKIP_IDENTICAL,
  checkSpace,
  collectDropFiles,
  dirnameUploadPath,
  ensureDirectory,
  fetchStorage,
  fetchUploadLimit,
  formatBytes,
  joinUploadPath,
  uploadWithProgress,
} from "../utils/upload.utils.js";

/** @type {UploadState} */
const initialState = {
  // idle | preparing (reading the drop) | blocked | running | cancelling
  // | refreshing (reloading the tree after the bytes are saved) | done
  phase: "idle",
  totalBytes: 0,
  doneBytes: 0,
  totalFiles: 0,
  doneFiles: 0,
  // Progress while the dropped folder is still being enumerated. A large
  // folder can take a while before the first byte is sent; these make that
  // phase visible and cancellable.
  scanFiles: 0,
  scanBytes: 0,
  uploaded: 0,
  skipped: 0,
  failed: 0,
  queued: 0,
  currentName: "",
  failures: [],
  blocked: null, // { problems: [{ message, ... }] } while waiting for the user
  message: "",
  bytesPerSecond: 0,
  fatal: false,
  conflict: UPLOAD_CONFLICT_SKIP_IDENTICAL,
};

/**
 * @typedef {"idle" | "preparing" | "blocked" | "running" | "cancelling" | "refreshing" | "done"} UploadPhase
 */

/**
 * @typedef {Object} SpaceProblem
 * @property {string} target
 * @property {number} needed
 * @property {number} free
 * @property {string} message
 */

/**
 * @typedef {Object} UploadFailure
 * @property {string} name
 * @property {string} reason
 * @property {boolean} retryable
 * @property {File} file
 * @property {string} relativePath
 * @property {string} targetPath
 */

/**
 * @typedef {Object} UploadItem
 * @property {File} file
 * @property {string} relativePath
 * @property {string} targetPath
 */

/**
 * @typedef {Object} UploadState
 * @property {UploadPhase} phase
 * @property {number} totalBytes
 * @property {number} doneBytes
 * @property {number} totalFiles
 * @property {number} doneFiles
 * @property {number} scanFiles
 * @property {number} scanBytes
 * @property {number} uploaded
 * @property {number} skipped
 * @property {number} failed
 * @property {number} queued
 * @property {string} currentName
 * @property {UploadFailure[]} failures
 * @property {{ problems: SpaceProblem[] } | null} blocked
 * @property {string} message
 * @property {number} bytesPerSecond
 * @property {boolean} fatal
 * @property {string} conflict
 */

/**
 * One queued drop, before it is split into items and failures.
 * @typedef {Object} BatchOptions
 * @property {FileSystemEntry[]} [entries]
 * @property {File[]} [files]
 * @property {string} [targetPath]
 * @property {Map<string, number | undefined>} [existing]
 * @property {string} [conflict]
 * @property {(() => Promise<void>) | null} [onComplete]
 */

/**
 * A started drop, kept while the free-space prompt is open.
 * @typedef {Object} Batch
 * @property {UploadItem[]} items
 * @property {string} conflict
 * @property {number} skipped
 * @property {number} totalBytes
 * @property {UploadFailure[]} failures
 */

export const upload = writable({ ...initialState });

// ========== MODULE-LEVEL RUNTIME ==========
let running = false;
let cancelled = false;
let fatal = false;
/** @type {Map<string, Promise<string>>} */
let ensuredDirs = new Map();
/** @type {AbortController | null} */
let activeController = null;
/** @type {AbortController | null} */
let scanController = null;
/** @type {BatchOptions[]} */
let queuedBatches = [];
/** @type {Batch | null} */
let pendingBlock = null;
/** @type {(() => Promise<void>) | null} */
let lastOnComplete = null;
/** @type {ReturnType<typeof setInterval> | null} */
let speedTimer = null;
let lastSample = { bytes: 0, time: 0 };
let lastScanReport = 0;
let maxUploadBytes = 0;
let sessionExpired = false;

/** Cache MAX_UPLOAD_MB exposed by /api/version. */
export async function loadUploadLimit() {
  try {
    maxUploadBytes = await fetchUploadLimit();
  } catch (error) {
    console.warn("Could not read the upload limit:", error);
  }
  return maxUploadBytes;
}

/**
 * @param {Partial<UploadState>} patch
 */
function updateState(patch) {
  upload.update((state) => ({ ...state, ...patch }));
}

/**
 * Queue a drop. Additional drops while an upload is running are queued and
 * started once the current batch finishes.
 *
 * @param {BatchOptions} [options]
 */
export async function startDrop({
  entries = [],
  files = [],
  targetPath = "",
  existing = new Map(),
  conflict = UPLOAD_CONFLICT_SKIP_IDENTICAL,
  onComplete = null,
} = {}) {
  const options = {
    entries,
    files,
    targetPath,
    existing,
    conflict,
    onComplete,
  };

  if (running) {
    queuedBatches.push(options);
    updateState({ queued: queuedBatches.length });
    return;
  }

  await runBatch(options);
}

/**
 * @param {BatchOptions} options
 */
async function runBatch(options) {
  running = true;
  cancelled = false;
  fatal = false;
  sessionExpired = false;
  ensuredDirs = new Map();
  pendingBlock = null;
  lastOnComplete = options.onComplete ?? null;

  const {
    entries = [],
    files = [],
    targetPath = "",
    existing = new Map(),
    conflict = UPLOAD_CONFLICT_SKIP_IDENTICAL,
  } = options;

  upload.set({
    ...initialState,
    phase: "preparing",
    conflict,
    queued: queuedBatches.length,
  });

  if (!maxUploadBytes) await loadUploadLimit();

  // Reading a dropped folder is the only phase that can take minutes for a
  // large tree before any byte moves. Keep it cancellable and show the count.
  lastScanReport = 0;
  scanController = new AbortController();
  // A Cancel that landed while the upload limit was loading has no scan to
  // abort yet, so carry it over instead of starting the walk.
  if (cancelled) scanController.abort();

  let dropped;
  try {
    dropped = await collectDropFiles(entries, files, {
      signal: scanController.signal,
      onProgress: ({ files: found, bytes }) => {
        const now = Date.now();
        if (now - lastScanReport < 120) return;
        lastScanReport = now;
        updateState({ scanFiles: found, scanBytes: bytes });
      },
    });
  } catch (caught) {
    const error = asUploadError(caught);
    scanController = null;
    if (cancelled || error.name === "AbortError") {
      await finishBatch("Upload cancelled.");
      return;
    }
    await finishBatch("Could not read the dropped files: " + error.message);
    return;
  }
  scanController = null;
  updateState({
    scanFiles: dropped.length,
    scanBytes: dropped.reduce((sum, entry) => sum + entry.file.size, 0),
  });

  if (!dropped.length) {
    toast.info("Nothing to upload in that drop.");
    await finishBatch("Nothing to upload in that drop.");
    return;
  }

  // Split the drop into files to send, identical files to skip and files that
  // can never succeed because they exceed the per-request limit.
  /** @type {UploadItem[]} */
  const items = [];
  /** @type {UploadFailure[]} */
  const failures = [];
  let skipped = 0;
  let totalBytes = 0;
  const largestSizes = [];

  for (const { file, relativePath } of dropped) {
    if (maxUploadBytes && file.size > maxUploadBytes) {
      failures.push({
        name: relativePath,
        reason: `Larger than the ${formatBytes(maxUploadBytes)} upload limit`,
        retryable: false,
        file,
        relativePath,
        targetPath,
      });
      continue;
    }

    const destination = joinUploadPath(targetPath, relativePath);
    const existingSize = existing.get(destination);
    if (
      conflict === UPLOAD_CONFLICT_SKIP_IDENTICAL &&
      existingSize !== undefined &&
      existingSize === file.size
    ) {
      skipped += 1;
      continue;
    }

    items.push({ file, relativePath, targetPath });
    totalBytes += file.size;
    // Track the files that can be in flight together so the temp-space check
    // matches what Werkzeug actually spools.
    largestSizes.push(file.size);
    largestSizes.sort((a, b) => b - a);
    if (largestSizes.length > UPLOAD_CONCURRENCY) {
      largestSizes.length = UPLOAD_CONCURRENCY;
    }
  }

  if (!items.length) {
    const hasFailures = failures.length > 0;
    const message = hasFailures
      ? "No files could be queued."
      : "Everything in that drop is already in the library.";
    upload.set({
      ...initialState,
      phase: "done",
      conflict,
      queued: queuedBatches.length,
      skipped,
      failed: failures.length,
      failures,
      message,
    });
    if (!hasFailures) toast.info("Everything in that drop is already there.");
    await finishBatch(message);
    return;
  }

  updateState({
    totalBytes,
    totalFiles: items.length,
    skipped,
    failures,
    failed: failures.length,
  });

  // Free-space preflight. If /api/storage is unavailable (older backend) the
  // upload proceeds; the per-file error handling still covers ENOSPC.
  let storage = null;
  try {
    storage = await fetchStorage();
  } catch (error) {
    console.warn("Storage preflight skipped:", error);
  }

  const tempPeak = largestSizes.reduce((sum, size) => sum + size, 0);
  const problems = storage ? checkSpace(storage, totalBytes, tempPeak) : [];
  if (problems.length) {
    pendingBlock = { items, conflict, skipped, totalBytes, failures };
    updateState({
      phase: "blocked",
      message: problems[0].message,
      blocked: { problems },
    });
    return; // running stays true so a new drop is queued, not raced
  }

  if (cancelled) {
    await finishBatch("Upload cancelled.");
    return;
  }

  await continueBatch({ items, conflict, skipped, totalBytes, failures });
}

/** User chose to upload despite the preflight warning. */
export async function proceedAnyway() {
  if (uploadState().phase !== "blocked" || !pendingBlock) return;
  const batch = pendingBlock;
  pendingBlock = null;
  await continueBatch(batch);
}

/**
 * @param {Batch} batch
 */
async function continueBatch({
  items,
  conflict,
  skipped,
  totalBytes,
  failures,
}) {
  updateState({
    phase: "running",
    blocked: null,
    message: "",
    totalBytes,
    totalFiles: items.length,
    skipped,
    failures,
    failed: failures.length,
  });

  startSpeedSampler();

  try {
    await runQueue(items, conflict);
  } finally {
    stopSpeedSampler();
  }

  await finishBatch(completionMessage());
}

function completionMessage() {
  if (sessionExpired) return "Session expired. Please log in again.";
  if (fatal) return "Upload stopped: the server is out of disk space.";
  if (cancelled) return "Upload cancelled.";
  return "";
}

function uploadState() {
  return get(upload);
}

/**
 * @param {unknown} error
 * @returns {import("../utils/upload.utils.js").UploadError}
 */
function asUploadError(error) {
  return /** @type {import("../utils/upload.utils.js").UploadError} */ (error);
}

/**
 * @param {UploadItem[]} items
 * @param {string} conflict
 */
async function runQueue(items, conflict) {
  const queue = items.slice();
  // Per-file high-water marks. Bytes are never removed, so the bar cannot
  // jump back when a file completes (its partial is replaced by its final
  // size) or when a retry restarts the request from zero.
  /** @type {Map<UploadItem, number>} */
  const itemBytes = new Map();
  let peakDoneBytes = 0;

  const controller = new AbortController();
  activeController = controller;

  const publishProgress = () => {
    let processed = 0;
    for (const bytes of itemBytes.values()) processed += bytes;
    const total = get(upload).totalBytes;
    const doneBytes = Math.max(
      peakDoneBytes,
      Math.min(total, Math.round(processed)),
    );
    peakDoneBytes = doneBytes;
    updateState({ doneBytes });
  };

  /**
   * @param {UploadItem} item
   * @param {string} reason
   * @param {boolean} retryable
   */
  const recordFailure = (item, reason, retryable) => {
    // Keep the bytes this file already transmitted. The bar tracks processed
    // bytes, so a failed file must not pull it backwards; the failure itself
    // is reported separately.
    publishProgress();
    upload.update((state) => ({
      ...state,
      failed: state.failed + 1,
      currentName: item.relativePath,
      failures: [
        ...state.failures,
        {
          name: item.relativePath,
          reason,
          retryable,
          file: item.file,
          relativePath: item.relativePath,
          targetPath: item.targetPath,
        },
      ],
    }));
  };

  /**
   * @param {UploadItem} item
   */
  const uploadOne = async (item) => {
    const directory = dirnameUploadPath(item.relativePath);
    const destination = joinUploadPath(item.targetPath, directory);

    if (directory) {
      // Files in the same folder share one mkdir request instead of racing
      // each other; failures are not cached so a retry can try again.
      let ensuring = ensuredDirs.get(destination);
      if (!ensuring) {
        ensuring = ensureDirectory(destination, {
          signal: controller.signal,
        });
        ensuredDirs.set(destination, ensuring);
        ensuring.catch(() => {
          if (ensuredDirs.get(destination) === ensuring) {
            ensuredDirs.delete(destination);
          }
        });
      }
      try {
        await ensuring;
      } catch (caught) {
        const error = asUploadError(caught);
        if (cancelled || error.name === "AbortError") return;
        recordFailure(item, `Could not create folder: ${error.message}`, false);
        return;
      }
    }

    const send = () =>
      uploadWithProgress(item.file, {
        targetPath: destination,
        conflict,
        signal: controller.signal,
        onProgress: (loaded, total) => {
          if (!total) return;
          const ratio = Math.min(loaded / total, 1);
          const bytes = Math.max(
            itemBytes.get(item) || 0,
            item.file.size * ratio,
          );
          itemBytes.set(item, bytes);
          publishProgress();
        },
      });

    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const result = await send();

        // The response can land after the user pressed Cancel; do not count
        // a file the user already stopped.
        if (cancelled) return;

        itemBytes.set(item, item.file.size);
        publishProgress();
        upload.update((state) => ({
          ...state,
          doneFiles: state.doneFiles + 1,
          uploaded: state.uploaded + (result?.skipped ? 0 : 1),
          skipped: state.skipped + (result?.skipped ? 1 : 0),
          currentName: item.relativePath,
        }));
        return;
      } catch (caught) {
        const error = asUploadError(caught);
        if (error.aborted || cancelled || error.status === 401) {
          if (error.status === 401) {
            cancelled = true;
            sessionExpired = true;
            updateState({
              phase: "cancelling",
              message: "Session expired. Please log in again.",
            });
            controller.abort();
            logout();
          }
          return;
        }

        if (error.status === 413) {
          recordFailure(item, error.message, false);
          return;
        }

        if (isOutOfSpace(error.message)) {
          fatal = true;
          cancelled = true;
          recordFailure(item, error.message, false);
          updateState({
            phase: "cancelling",
            message: "Upload stopped: the server is out of disk space.",
          });
          controller.abort();
          return;
        }

        if (error.retryable && attempt === 0 && !cancelled) {
          // A retry is safe: skip-identical makes a repeated upload idempotent.
          continue;
        }

        recordFailure(item, error.message, Boolean(error.retryable));
        return;
      }
    }
  };

  const worker = async () => {
    while (queue.length && !cancelled) {
      const item = queue.shift();
      if (!item) return;

      await uploadOne(item);
    }
  };

  /** @type {Promise<void>[]} */
  const workers = [];
  const workerCount = Math.min(UPLOAD_CONCURRENCY, queue.length);
  for (let index = 0; index < workerCount; index += 1) {
    workers.push(worker());
  }

  await Promise.all(workers);
  activeController = null;
}

/**
 * @param {unknown} message
 * @returns {boolean}
 */
function isOutOfSpace(message) {
  return /out of disk space/i.test(String(message || ""));
}

function startSpeedSampler() {
  stopSpeedSampler();
  lastSample = { bytes: get(upload).doneBytes, time: Date.now() };
  speedTimer = setInterval(() => {
    const state = get(upload);
    if (state.phase !== "running") return;

    const now = Date.now();
    const elapsed = (now - lastSample.time) / 1000;
    if (elapsed <= 0) return;

    const delta = Math.max(0, state.doneBytes - lastSample.bytes);
    const instant = delta / elapsed;
    const smoothed =
      state.bytesPerSecond > 0
        ? state.bytesPerSecond * 0.7 + instant * 0.3
        : instant;

    lastSample = { bytes: state.doneBytes, time: now };
    updateState({ bytesPerSecond: smoothed });
  }, 1000);
}

function stopSpeedSampler() {
  if (speedTimer) {
    clearInterval(speedTimer);
    speedTimer = null;
  }
}

/**
 * @param {string} message
 */
async function finishBatch(message) {
  stopSpeedSampler();
  scanController = null;

  const state = uploadState();
  // Nothing to reload when the batch was cancelled before it sent anything or
  // when every file was already in the library. Reloading a large tree is the
  // next slow step after the bytes are saved, so skip it when possible.
  const changed = state.uploaded > 0 || ensuredDirs.size > 0;
  const refresh = Boolean(lastOnComplete) && !sessionExpired && changed;

  updateState({
    phase: refresh ? "refreshing" : "done",
    currentName: "",
    message,
    bytesPerSecond: 0,
  });

  if (refresh && lastOnComplete) {
    try {
      await lastOnComplete();
    } catch (error) {
      console.error("Upload post-processing failed:", error);
    }

    // Dismissing the tray or a late state change while the tree was reloading
    // must not bring it back.
    upload.update((current) =>
      current.phase === "refreshing" ? { ...current, phase: "done" } : current,
    );
  }

  running = false;
  cancelled = false;
  sessionExpired = false;

  if (queuedBatches.length) {
    const next = queuedBatches.shift();
    updateState({ queued: queuedBatches.length });
    if (next) await runBatch(next);
  }
}

/** Cancel the running batch. Files already received stay in the library. */
export function cancel() {
  if (!running) return;

  const phase = uploadState().phase;
  // Once the bytes are saved there is nothing to cancel: the tree is only
  // being reloaded. Ignoring the click here also stops a second Cancel press
  // from flipping a finished batch back to "Cancelling…".
  if (phase === "done" || phase === "refreshing") return;

  // Cancelling stops the whole upload session, not just the current batch.
  const hadQueued = queuedBatches.length > 0;
  queuedBatches = [];
  if (hadQueued) updateState({ queued: 0 });

  if (pendingBlock) {
    // Still waiting on the free-space decision; nothing has been sent yet.
    pendingBlock = null;
    cancelled = true;
    running = false;
    updateState({
      phase: "done",
      blocked: null,
      message: "Upload cancelled.",
    });
    return;
  }

  cancelled = true;
  updateState({ phase: "cancelling", message: "Cancelling…" });
  // The scan has its own controller because it runs before the upload queue
  // is created; aborting it makes cancelling a large folder immediate.
  scanController?.abort();
  activeController?.abort();
}

/** Retry failures that look transient. Safe because duplicates are skipped. */
export async function retryFailed() {
  if (running) return;

  const state = get(upload);
  const retryable = state.failures.filter((failure) => failure.retryable);
  if (!retryable.length) return;

  const retained = state.failures.filter((failure) => !failure.retryable);
  const items = retryable
    .filter((failure) => failure.file)
    .map((failure) => ({
      file: failure.file,
      relativePath: failure.relativePath,
      targetPath: failure.targetPath || "",
    }));

  if (!items.length) return;

  running = true;
  cancelled = false;
  fatal = false;
  sessionExpired = false;
  ensuredDirs = new Map();

  upload.update((current) => ({
    ...current,
    phase: "running",
    totalBytes: items.reduce((sum, item) => sum + item.file.size, 0),
    doneBytes: 0,
    totalFiles: items.length,
    doneFiles: 0,
    uploaded: 0,
    skipped: 0,
    failures: retained,
    failed: retained.length,
    currentName: "",
    message: "",
    blocked: null,
    bytesPerSecond: 0,
    fatal: false,
  }));

  startSpeedSampler();
  try {
    await runQueue(items, state.conflict);
  } finally {
    stopSpeedSampler();
  }
  await finishBatch(completionMessage());
}

/** Hide the tray and release the retained File references. */
export function dismiss() {
  // A finished upload waits in "refreshing" while the tree reloads; dismissing
  // that is harmless because the files are already saved.
  if (running && uploadState().phase !== "refreshing") return;
  upload.set({ ...initialState });
}
