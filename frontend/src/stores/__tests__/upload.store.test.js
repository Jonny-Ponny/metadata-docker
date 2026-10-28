import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

const mocks = vi.hoisted(() => ({
  collectDropFiles: vi.fn(),
  ensureDirectory: vi.fn(),
  fetchStorage: vi.fn(),
  checkSpace: vi.fn(),
  fetchUploadLimit: vi.fn(),
  uploadWithProgress: vi.fn(),
}));

vi.mock("../../utils/upload.utils.js", () => ({
  UPLOAD_CONCURRENCY: 2,
  UPLOAD_CONFLICT_SKIP_IDENTICAL: "skip-identical",
  collectDropFiles: mocks.collectDropFiles,
  ensureDirectory: mocks.ensureDirectory,
  fetchStorage: mocks.fetchStorage,
  checkSpace: mocks.checkSpace,
  fetchUploadLimit: mocks.fetchUploadLimit,
  uploadWithProgress: mocks.uploadWithProgress,
  formatBytes: (/** @type {number} */ bytes) => `${bytes} B`,
  joinUploadPath: (/** @type {string[]} */ ...parts) =>
    parts.filter(Boolean).join("/"),
  dirnameUploadPath: (/** @type {string} */ path) =>
    path.includes("/") ? path.split("/").slice(0, -1).join("/") : "",
}));

/** @type {typeof import("../upload.store.js")} */
let store;

/**
 * @param {string} name
 * @param {number} [size]
 */
function file(name, size = 10) {
  return new File(["x".repeat(size)], name, { type: "audio/mpeg" });
}

/**
 * @param {import("../upload.store.js").UploadPhase} phase
 */
async function waitForPhase(phase) {
  await vi.waitFor(() => expect(get(store.upload).phase).toBe(phase));
}

describe("upload store", () => {
  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();
    mocks.collectDropFiles.mockImplementation(
      async (/** @type {unknown} */ _entries, /** @type {File[]} */ files) =>
        files.map((item) => ({ file: item, relativePath: item.name })),
    );
    mocks.ensureDirectory.mockResolvedValue(undefined);
    mocks.fetchStorage.mockResolvedValue({ free: 10_000 });
    mocks.checkSpace.mockReturnValue([]);
    mocks.fetchUploadLimit.mockResolvedValue(1000);
    mocks.uploadWithProgress.mockResolvedValue({ skipped: false });

    store = await import("../upload.store.js");
    await store.loadUploadLimit();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reads the upload limit from the API", async () => {
    mocks.fetchUploadLimit.mockClear();
    mocks.fetchUploadLimit.mockResolvedValue(2048);

    await expect(store.loadUploadLimit()).resolves.toBe(2048);
    expect(mocks.fetchUploadLimit).toHaveBeenCalledTimes(1);
  });

  it("reuses the loaded limit for later batches", async () => {
    mocks.fetchUploadLimit.mockClear();

    await store.startDrop({ files: [file("a.mp3")] });

    expect(mocks.fetchUploadLimit).not.toHaveBeenCalled();
    expect(mocks.uploadWithProgress).toHaveBeenCalledTimes(1);
  });

  it("treats a missing upload limit as unlimited", async () => {
    mocks.fetchUploadLimit.mockRejectedValue(new Error("offline"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(store.loadUploadLimit()).resolves.toBe(1000);
    expect(warn).toHaveBeenCalled();
  });

  it("uploads a drop and reports the totals", async () => {
    const onComplete = vi.fn().mockResolvedValue(undefined);
    const first = file("a.mp3", 10);
    const second = file("b.mp3", 20);

    await store.startDrop({
      files: [first, second],
      targetPath: "music",
      onComplete,
    });

    const state = get(store.upload);
    expect(state.phase).toBe("done");
    expect(state.uploaded).toBe(2);
    expect(state.doneFiles).toBe(2);
    expect(state.totalBytes).toBe(30);
    expect(state.doneBytes).toBe(30);
    expect(state.failed).toBe(0);
    expect(state.message).toBe("");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(mocks.uploadWithProgress).toHaveBeenCalledTimes(2);
  });

  it("keeps the tray in the refreshing phase while the tree reloads", async () => {
    /** @type {() => void} */
    let release = () => {};
    const onComplete = vi.fn(
      () =>
        new Promise((resolve) => {
          release = () => resolve(undefined);
        }),
    );

    const pending = store.startDrop({ files: [file("a.mp3")], onComplete });
    await waitForPhase("refreshing");

    release();
    await pending;

    expect(get(store.upload).phase).toBe("done");
  });

  it("creates each destination folder once", async () => {
    await store.startDrop({
      files: [file("one.mp3"), file("two.mp3")],
      targetPath: "music",
    });

    await store.startDrop({
      files: [file("nested/one.mp3"), file("nested/two.mp3")],
      targetPath: "music",
    });

    expect(mocks.ensureDirectory).toHaveBeenCalledTimes(1);
    expect(mocks.ensureDirectory).toHaveBeenCalledWith("music/nested", {
      signal: expect.any(AbortSignal),
    });
    expect(mocks.uploadWithProgress).toHaveBeenLastCalledWith(
      expect.any(File),
      expect.objectContaining({ targetPath: "music/nested" }),
    );
  });

  it("skips identical files and reports an unchanged drop", async () => {
    const existing = new Map([["music/a.mp3", 10]]);

    await store.startDrop({
      files: [file("a.mp3", 10)],
      targetPath: "music",
      existing,
    });

    const state = get(store.upload);
    expect(state.phase).toBe("done");
    expect(state.skipped).toBe(1);
    expect(state.uploaded).toBe(0);
    expect(state.message).toBe(
      "Everything in that drop is already in the library.",
    );
    expect(mocks.uploadWithProgress).not.toHaveBeenCalled();
  });

  it("queues files larger than the upload limit", async () => {
    await store.startDrop({ files: [file("huge.flac", 2000)] });

    const state = get(store.upload);
    expect(state.phase).toBe("done");
    expect(state.failed).toBe(1);
    expect(state.failures[0]).toMatchObject({
      name: "huge.flac",
      retryable: false,
      reason: "Larger than the 1000 B upload limit",
    });
    expect(state.message).toBe("No files could be queued.");
  });

  it("reports an empty drop", async () => {
    await store.startDrop({ files: [] });

    expect(get(store.upload).phase).toBe("done");
    expect(get(store.upload).message).toBe("Nothing to upload in that drop.");
  });

  it("blocks on the free-space preflight until the user proceeds", async () => {
    mocks.checkSpace.mockReturnValue([
      { target: "/tmp", needed: 100, free: 1, message: "Not enough space" },
    ]);

    await store.startDrop({ files: [file("a.mp3")], targetPath: "music" });

    expect(get(store.upload).phase).toBe("blocked");
    expect(get(store.upload).blocked?.problems).toHaveLength(1);
    expect(mocks.uploadWithProgress).not.toHaveBeenCalled();

    await store.proceedAnyway();

    expect(get(store.upload).phase).toBe("done");
    expect(mocks.uploadWithProgress).toHaveBeenCalledTimes(1);
  });

  it("cancels a running upload", async () => {
    /** @type {(error: unknown) => void} */
    let failUpload = () => {};
    mocks.uploadWithProgress.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          failUpload = reject;
        }),
    );

    const pending = store.startDrop({ files: [file("a.mp3")] });
    await waitForPhase("running");

    store.cancel();

    expect(get(store.upload).phase).toBe("cancelling");
    expect(get(store.upload).message).toBe("Cancelling…");

    failUpload({ name: "AbortError", aborted: true, message: "aborted" });
    await pending;

    expect(get(store.upload).phase).toBe("done");
    expect(get(store.upload).message).toBe("Upload cancelled.");
  });

  it("cancels a blocked batch before anything is sent", async () => {
    mocks.checkSpace.mockReturnValue([
      { target: "/tmp", needed: 100, free: 1, message: "Not enough space" },
    ]);
    await store.startDrop({ files: [file("a.mp3")] });

    store.cancel();

    expect(get(store.upload).phase).toBe("done");
    expect(get(store.upload).message).toBe("Upload cancelled.");
    expect(get(store.upload).blocked).toBeNull();
  });

  it("retries the transient failures", async () => {
    mocks.uploadWithProgress.mockRejectedValue({
      name: "Error",
      message: "Network error",
      retryable: true,
    });

    await store.startDrop({ files: [file("a.mp3")] });

    expect(get(store.upload).failures).toHaveLength(1);
    expect(get(store.upload).failures[0].retryable).toBe(true);

    mocks.uploadWithProgress.mockResolvedValue({ skipped: false });
    await store.retryFailed();

    expect(get(store.upload).phase).toBe("done");
    expect(get(store.upload).uploaded).toBe(1);
    expect(get(store.upload).failures).toHaveLength(0);
  });

  it("stops and logs out when the session expires", async () => {
    localStorage.setItem("auth_token", "token");
    mocks.uploadWithProgress.mockRejectedValue({
      name: "Error",
      message: "Unauthorized",
      status: 401,
    });

    await store.startDrop({ files: [file("a.mp3")] });

    expect(get(store.upload).message).toBe(
      "Session expired. Please log in again.",
    );
    expect(localStorage.getItem("auth_token")).toBeNull();
  });

  it("records a 413 as a permanent failure", async () => {
    mocks.uploadWithProgress.mockRejectedValue({
      name: "Error",
      message: "File too large",
      status: 413,
    });

    await store.startDrop({ files: [file("a.mp3")] });

    expect(get(store.upload).failed).toBe(1);
    expect(get(store.upload).failures[0]).toMatchObject({
      reason: "File too large",
      retryable: false,
    });
  });

  it("stops the batch when the server runs out of disk space", async () => {
    mocks.uploadWithProgress.mockRejectedValue({
      name: "Error",
      message: "The server is out of disk space",
    });

    await store.startDrop({ files: [file("a.mp3"), file("b.mp3")] });

    expect(get(store.upload).message).toBe(
      "Upload stopped: the server is out of disk space.",
    );
    expect(get(store.upload).failed).toBe(1);
  });

  it("waits for the running batch before starting a queued drop", async () => {
    /** @type {(() => void)[]} */
    const releases = [];
    mocks.uploadWithProgress.mockImplementation(
      () =>
        new Promise((resolve) => {
          releases.push(() => resolve({ skipped: false }));
        }),
    );

    const first = store.startDrop({ files: [file("a.mp3")] });
    await waitForPhase("running");
    const second = store.startDrop({ files: [file("b.mp3")] });

    expect(get(store.upload).queued).toBe(1);

    releases[0]();
    await vi.waitFor(() => expect(releases).toHaveLength(2));
    releases[1]();
    await second;
    await first;

    expect(get(store.upload).queued).toBe(0);
    // Each batch owns its own counters, so the finished state is the queued drop.
    expect(get(store.upload).uploaded).toBe(1);
    expect(mocks.uploadWithProgress).toHaveBeenCalledTimes(2);
  });

  it("only dismisses a batch that is not sending", async () => {
    /** @type {() => void} */
    let release = () => {};
    mocks.uploadWithProgress.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ skipped: false });
        }),
    );

    const pending = store.startDrop({ files: [file("a.mp3")] });
    await waitForPhase("running");
    store.dismiss();
    expect(get(store.upload).phase).toBe("running");

    release();
    await pending;
    store.dismiss();

    expect(get(store.upload).phase).toBe("idle");
    expect(get(store.upload).failures).toEqual([]);
  });
});
