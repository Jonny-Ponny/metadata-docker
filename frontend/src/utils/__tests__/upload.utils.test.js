// @ts-check
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../version.utils.js", () => ({
  fetchVersionInfo: vi.fn(),
}));

import { fetchVersionInfo } from "../version.utils.js";
import { authToken } from "../../stores/auth.store.js";
import {
  UPLOAD_CONFLICT_KEEP_BOTH,
  UPLOAD_CONFLICT_SKIP_IDENTICAL,
  buildExistingIndex,
  checkSpace,
  collectDropFiles,
  dirnameUploadPath,
  ensureDirectory,
  fetchStorage,
  fetchUploadLimit,
  formatBytes,
  formatDuration,
  isJunkPath,
  joinUploadPath,
  uploadWithProgress,
} from "../upload.utils.js";

/**
 * Enough of XMLHttpRequest for the upload helper: the properties it assigns and
 * the events it fires back.
 */
class FakeXHR {
  /** @type {FakeXHR[]} */
  static instances = [];

  /** @type {{ onprogress: (event: any) => void }} */
  upload = { onprogress: () => {} };
  /** @type {Record<string, string>} */
  headers = {};
  /** @type {boolean} */
  sent = false;
  /** @type {string} */
  method = "";
  /** @type {string} */
  url = "";
  /** @type {any} */
  body;
  /** @type {boolean} */
  aborted = false;
  /** @type {number} */
  status = 0;
  /** @type {string} */
  responseText = "";
  /** @type {() => void} */
  onabort = () => {};
  /** @type {() => void} */
  onload = () => {};
  /** @type {() => void} */
  onerror = () => {};
  /** @type {() => void} */
  ontimeout = () => {};

  constructor() {
    FakeXHR.instances.push(this);
  }

  /**
   * @param {string} method
   * @param {string} url
   */
  open(method, url) {
    this.method = method;
    this.url = url;
  }

  /**
   * @param {string} name
   * @param {string} value
   */
  setRequestHeader(name, value) {
    this.headers[name] = value;
  }

  /** @param {any} body */
  send(body) {
    this.body = body;
    this.sent = true;
  }

  abort() {
    this.aborted = true;
    this.onabort?.();
  }

  /**
   * @param {number} status
   * @param {string} text
   */
  respond(status, text) {
    this.status = status;
    this.responseText = text;
    this.onload?.();
  }
}

/** @returns {FakeXHR} */
function lastXHR() {
  const xhr = FakeXHR.instances.at(-1);
  if (!xhr) throw new Error("No XMLHttpRequest was created");
  return xhr;
}

/**
 * Minimal Response stub for the fetch mocks.
 * @param {number} status
 * @param {string} text
 * @param {boolean} [ok]
 */
const jsonResponse = (status, text, ok = true) => ({
  ok,
  status,
  text: async () => text,
});

/**
 * The upload helpers only read `name`, `size` and `webkitRelativePath`, so the
 * tests use plain objects and cast them at the boundary.
 * @param {Array<{ name: string, size: number, webkitRelativePath?: string }>} items
 * @returns {File[]}
 */
const asFiles = (items) =>
  /** @type {File[]} */ (/** @type {unknown} */ (items));

/**
 * @param {string} name
 * @param {Record<string, any>} [file]
 * @returns {FileSystemFileEntry}
 */
const fileEntry = (name, file = {}) =>
  /** @type {FileSystemFileEntry} */ (
    /** @type {unknown} */ ({
      name,
      isFile: true,
      isDirectory: false,
      file: (/** @type {(value: any) => void} */ resolve) =>
        resolve({ name, size: 1, ...file }),
    })
  );

/**
 * @param {string} name
 * @param {FileSystemEntry[][]} batches
 * @returns {FileSystemDirectoryEntry}
 */
const directoryEntry = (name, batches) => {
  let batchIndex = 0;
  return /** @type {FileSystemDirectoryEntry} */ (
    /** @type {unknown} */ ({
      name,
      isFile: false,
      isDirectory: true,
      createReader() {
        return /** @type {FileSystemDirectoryReader} */ (
          /** @type {unknown} */ ({
            /**
             * @param {(value: FileSystemEntry[]) => void} resolve
             */
            readEntries: (resolve) => {
              const batch = batches[batchIndex] ?? [];
              batchIndex += 1;
              resolve(batch);
            },
          })
        );
      },
    })
  );
};

beforeEach(() => {
  FakeXHR.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  authToken.set("test-token");
});

afterEach(() => {
  vi.unstubAllGlobals();
  authToken.set(null);
});

describe("isJunkPath", () => {
  it("detects OS metadata files", () => {
    expect(isJunkPath(".DS_Store")).toBe(true);
    expect(isJunkPath("Album/.DS_Store")).toBe(true);
    expect(isJunkPath("Album/._track.mp3")).toBe(true);
    expect(isJunkPath("Thumbs.db")).toBe(true);
    expect(isJunkPath("desktop.ini")).toBe(true);
  });

  it("detects junk directories anywhere in the path", () => {
    expect(isJunkPath("__MACOSX/album/track.mp3")).toBe(true);
    expect(isJunkPath("album/@eaDir/track.mp3")).toBe(true);
    expect(isJunkPath("album/.Trashes")).toBe(true);
  });

  it("allows ordinary music paths", () => {
    expect(isJunkPath("Album/CD1/01 - Track.mp3")).toBe(false);
    expect(isJunkPath("")).toBe(false);
    expect(isJunkPath(null)).toBe(false);
  });
});

describe("path helpers", () => {
  it("joins defined path parts", () => {
    expect(joinUploadPath("Album", "CD1", "track.mp3")).toBe(
      "Album/CD1/track.mp3",
    );
    expect(joinUploadPath("", null, undefined, "track.mp3")).toBe("track.mp3");
  });

  it("returns the parent directory of an upload path", () => {
    expect(dirnameUploadPath("Album/CD1/track.mp3")).toBe("Album/CD1");
    expect(dirnameUploadPath("track.mp3")).toBe("");
    expect(dirnameUploadPath("")).toBe("");
    expect(dirnameUploadPath(null)).toBe("");
  });
});

describe("buildExistingIndex", () => {
  it("indexes every file path with its size", () => {
    const tree = [
      {
        type: "directory",
        children: [
          { type: "file", path: "Album/one.mp3", size: 1 },
          {
            type: "directory",
            children: [{ type: "file", path: "Album/CD2/two.flac", size: 2 }],
          },
        ],
      },
      { type: "file", path: "loose.wav", size: 3 },
      null,
    ];

    expect([...buildExistingIndex(/** @type {any} */ (tree))]).toEqual([
      ["Album/one.mp3", 1],
      ["Album/CD2/two.flac", 2],
      ["loose.wav", 3],
    ]);
  });
});

describe("collectDropFiles", () => {
  it("uses webkitRelativePath and filters junk", async () => {
    const onProgress = vi.fn();
    const files = [
      { name: "one.mp3", size: 10, webkitRelativePath: "Album/one.mp3" },
      { name: ".DS_Store", size: 1, webkitRelativePath: "Album/.DS_Store" },
      { name: "two.flac", size: 20, webkitRelativePath: "Album/two.flac" },
    ];

    const result = await collectDropFiles([], asFiles(files), { onProgress });

    expect(result.map((entry) => entry.relativePath)).toEqual([
      "Album/one.mp3",
      "Album/two.flac",
    ]);
    expect(onProgress).toHaveBeenCalledWith({ files: 2, bytes: 30 });
  });

  it("uses file names when there is no relative path", async () => {
    const result = await collectDropFiles(
      [],
      asFiles([
        { name: "one.mp3", size: 10 },
        { name: "._one.mp3", size: 1 },
      ]),
    );

    expect(result).toEqual([
      { file: { name: "one.mp3", size: 10 }, relativePath: "one.mp3" },
    ]);
  });

  it("walks directory entries recursively", async () => {
    const onProgress = vi.fn();
    const root = directoryEntry("Album", [
      [
        fileEntry("01.mp3", { size: 10 }),
        directoryEntry("CD2", [[fileEntry("02.flac", { size: 20 })], []]),
        directoryEntry("__MACOSX", [[fileEntry("._01.mp3", { size: 1 })], []]),
      ],
      [],
    ]);

    const result = await collectDropFiles([root], [], { onProgress });

    expect(result.map((entry) => entry.relativePath)).toEqual([
      "Album/01.mp3",
      "Album/CD2/02.flac",
    ]);
    expect(onProgress).toHaveBeenLastCalledWith({ files: 2, bytes: 30 });
  });

  it("rejects when the scan was already cancelled", async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      collectDropFiles([], [], { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it("stops walking when cancelled between files", async () => {
    const controller = new AbortController();
    const root = directoryEntry("Album", [
      [
        /** @type {FileSystemFileEntry} */ (
          /** @type {unknown} */ ({
            name: "slow.mp3",
            isFile: true,
            isDirectory: false,
            file: (/** @type {(value: any) => void} */ resolve) => {
              controller.abort();
              resolve({ name: "slow.mp3", size: 1 });
            },
          })
        ),
      ],
      [],
    ]);

    await expect(
      collectDropFiles([root], [], { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("ensureDirectory", () => {
  it("creates a folder with the merge policy", async () => {
    const fetchMock = vi.fn(
      async (/** @type {string} */ _url, /** @type {any} */ _options) =>
        jsonResponse(200, JSON.stringify({ path: "Album/CD1" })),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(ensureDirectory("Album/CD1")).resolves.toBe("Album/CD1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/mkdir");
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer test-token");
    expect(JSON.parse(options.body)).toEqual({
      path: "Album/CD1",
      conflict: "merge",
    });
  });

  it("returns the requested path when the response has no path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () => "not json",
      })),
    );

    await expect(ensureDirectory("Album")).resolves.toBe("Album");
  });

  it("throws the backend error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 409,
        text: async () => JSON.stringify({ error: "Folder is read-only" }),
      })),
    );

    await expect(ensureDirectory("Album")).rejects.toThrow(
      "Folder is read-only",
    );
  });

  it("adds the status to the fallback for non-JSON errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        text: async () => "<html>",
      })),
    );

    await expect(ensureDirectory("Album")).rejects.toThrow(
      "Could not create the destination folder (HTTP 500)",
    );
  });
});

describe("fetchStorage", () => {
  it("returns the storage payload with auth headers", async () => {
    const payload = { music: { free: 10 }, temp: { free: 20 } };
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(payload),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchStorage()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/storage", {
      headers: { Authorization: "Bearer test-token" },
    });
  });

  it("throws a readable error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        text: async () => JSON.stringify({ error: "Disk unavailable" }),
      })),
    );

    await expect(fetchStorage()).rejects.toThrow("Disk unavailable");
  });
});

describe("fetchUploadLimit", () => {
  it("reads max_upload_bytes from the version payload", async () => {
    vi.mocked(fetchVersionInfo).mockResolvedValue({ max_upload_bytes: 1024 });

    await expect(fetchUploadLimit()).resolves.toBe(1024);
  });

  it("falls back to 0 for a missing or invalid value", async () => {
    vi.mocked(fetchVersionInfo).mockResolvedValue({});
    await expect(fetchUploadLimit()).resolves.toBe(0);

    vi.mocked(fetchVersionInfo).mockResolvedValue({ max_upload_bytes: "nope" });
    await expect(fetchUploadLimit()).resolves.toBe(0);
  });
});

describe("uploadWithProgress", () => {
  const makeFile = () => new File(["hello"], "song.mp3");

  it("posts the file and resolves with the JSON response", async () => {
    const file = makeFile();
    const onProgress = vi.fn();
    const promise = uploadWithProgress(file, {
      targetPath: "Album",
      conflict: UPLOAD_CONFLICT_KEEP_BOTH,
      onProgress,
    });
    const xhr = lastXHR();

    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/upload");
    expect(xhr.headers.Authorization).toBe("Bearer test-token");
    expect(xhr.body.get("file")).toBe(file);
    expect(xhr.body.get("targetPath")).toBe("Album");
    expect(xhr.body.get("originalFilename")).toBe("song.mp3");
    expect(xhr.body.get("conflict")).toBe(UPLOAD_CONFLICT_KEEP_BOTH);

    xhr.upload.onprogress({ lengthComputable: false, loaded: 1, total: 5 });
    expect(onProgress).not.toHaveBeenCalled();

    xhr.upload.onprogress({ lengthComputable: true, loaded: 2, total: 5 });
    expect(onProgress).toHaveBeenCalledWith(2, 5);

    xhr.respond(200, JSON.stringify({ path: "Album/song.mp3" }));

    await expect(promise).resolves.toEqual({ path: "Album/song.mp3" });
    expect(onProgress).toHaveBeenLastCalledWith(5, 5);
  });

  it("defaults to the skip-identical conflict policy", async () => {
    const promise = uploadWithProgress(makeFile());
    const xhr = lastXHR();

    expect(xhr.body.get("conflict")).toBe(UPLOAD_CONFLICT_SKIP_IDENTICAL);

    xhr.respond(200, "{}");
    await expect(promise).resolves.toEqual({});
  });

  it("resolves with an empty object for an empty success body", async () => {
    const promise = uploadWithProgress(makeFile());
    lastXHR().respond(204, "");

    await expect(promise).resolves.toEqual({});
  });

  it("uses the backend error message for a rejected upload", async () => {
    const promise = uploadWithProgress(makeFile());
    lastXHR().respond(
      400,
      JSON.stringify({ error: "File type is not supported" }),
    );

    await expect(promise).rejects.toMatchObject({
      message: "File type is not supported",
      status: 400,
      retryable: false,
    });
  });

  it("marks 5xx responses as retryable", async () => {
    const promise = uploadWithProgress(makeFile());
    lastXHR().respond(503, "");

    await expect(promise).rejects.toMatchObject({
      message: "Upload failed (HTTP 503)",
      status: 503,
      retryable: true,
    });
  });

  it("marks network failures and timeouts as retryable", async () => {
    const network = uploadWithProgress(makeFile());
    lastXHR().onerror();
    await expect(network).rejects.toMatchObject({
      status: 0,
      retryable: true,
    });

    const timeout = uploadWithProgress(makeFile());
    lastXHR().ontimeout();
    await expect(timeout).rejects.toMatchObject({
      message: "The upload timed out.",
      status: 0,
      retryable: true,
    });
  });

  it("aborts when the signal fires", async () => {
    const controller = new AbortController();
    const promise = uploadWithProgress(makeFile(), {
      signal: controller.signal,
    });
    const xhr = lastXHR();

    controller.abort();

    expect(xhr.aborted).toBe(true);
    await expect(promise).rejects.toMatchObject({
      message: "Upload cancelled.",
      status: 0,
      aborted: true,
    });
  });

  it("does not send when the signal is already aborted", async () => {
    const controller = new AbortController();
    controller.abort();
    const promise = uploadWithProgress(makeFile(), {
      signal: controller.signal,
    });
    const xhr = lastXHR();

    expect(xhr.sent).toBe(false);
    await expect(promise).rejects.toMatchObject({ aborted: true });
  });
});

describe("checkSpace", () => {
  /**
   * @param {number} musicFree
   * @param {number} tempFree
   * @param {number} [headroom]
   */
  const storage = (musicFree, tempFree, headroom = 1024 * 1024) => ({
    headroom,
    music: { free: musicFree },
    temp: { free: tempFree },
  });

  it("accepts a small upload with enough room", () => {
    expect(checkSpace(storage(10_000, 10_000), 1_000, 1_000)).toEqual([]);
  });

  it("requires the library free space plus up to the headroom", () => {
    const problems = checkSpace(storage(1_019, 10_000), 1_000, 0);

    expect(problems).toEqual([
      {
        target: "library",
        needed: 1_000,
        free: 1_019,
        message:
          "Not enough space in the music library: need 1000 B, 1019 B free.",
      },
    ]);
  });

  it("caps the headroom at the configured value", () => {
    const problems = checkSpace(
      storage(105_906_175, 10_000, 1024 * 1024),
      100 * 1024 * 1024,
      0,
    );

    expect(problems[0]).toMatchObject({
      target: "library",
      needed: 100 * 1024 * 1024,
    });
  });

  it("checks the spool temp space above the spool threshold", () => {
    const problems = checkSpace(
      storage(10_000_000, 1024 * 1024),
      1_000,
      1024 * 1024,
    );

    expect(problems).toEqual([
      {
        target: "temp",
        needed: 1024 * 1024 * 1.1,
        free: 1024 * 1024,
        message:
          "Not enough temporary space for uploads: need about 1.1 MB, 1.0 MB free.",
      },
    ]);
  });

  it("ignores temp space when the peak is at or below the threshold", () => {
    expect(checkSpace(storage(10_000_000, 0), 1_000, 512 * 1024)).toEqual([]);
  });
});

describe("formatBytes", () => {
  it("formats each unit", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(100 * 1024)).toBe("100 KB");
    expect(formatBytes(1024 * 1024)).toBe("1.0 MB");
    expect(formatBytes(1024 ** 3)).toBe("1.0 GB");
  });

  it("treats missing values as zero", () => {
    expect(formatBytes(undefined)).toBe("0 B");
    expect(formatBytes("nope")).toBe("0 B");
  });
});

describe("formatDuration", () => {
  it("formats seconds, minutes and hours", () => {
    expect(formatDuration(0.4)).toBe("1 s");
    expect(formatDuration(59.4)).toBe("59 s");
    expect(formatDuration(60)).toBe("1 min");
    expect(formatDuration(90)).toBe("2 min");
    expect(formatDuration(3600)).toBe("1 h");
    expect(formatDuration(5400)).toBe("1 h 30 min");
    expect(formatDuration(7200)).toBe("2 h");
  });

  it("returns an empty string for unusable values", () => {
    expect(formatDuration(0)).toBe("");
    expect(formatDuration(-1)).toBe("");
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe("");
    expect(formatDuration(undefined)).toBe("");
  });
});
