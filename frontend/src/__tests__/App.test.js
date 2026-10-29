import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/svelte";
import { get } from "svelte/store";

import App from "../App.svelte";
import {
  authToken,
  isAuthenticated,
  tokenExpiry,
} from "../stores/auth.store.js";
import { renamingPath } from "../stores/context.store.js";
import { theme } from "../stores/theme.store.js";
import { toast } from "../stores/toast.store.js";
import { dismiss, upload } from "../stores/upload.store.js";
import { settings } from "../utils/settings.utils.js";

const startDropMock = vi.hoisted(() => vi.fn());

vi.mock("../utils/index.js", async (importOriginal) => {
  const actual = /** @type {Record<string, unknown>} */ (
    await importOriginal()
  );
  return { ...actual, startDrop: startDropMock };
});

const initialSettings = structuredClone(get(settings));

// jsdom does not implement these; keep them installed for the whole file so
// component teardown still works after each test.
Object.defineProperty(Element.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});
Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: vi.fn(),
});
let objectUrlCount = 0;
Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  value: vi.fn(() => `blob:test-${++objectUrlCount}`),
});
Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  value: vi.fn(),
});

const metadata = {
  title: "Song",
  album: "Album",
  artist: "Artist",
  albumArtist: "Album Artist",
  trackNumber: 3,
  diskNumber: 1,
  date: "2024",
  genre: "Rock",
  releaseType: "Album",
  composer: "Composer",
  comment: "Note",
  description: "Details",
  lyrics: "[00:01.00]line one",
  unsyncedLyrics: "line one",
  picture: null,
  hasPicture: true,
  customFields: {},
  otherFields: {},
  readOnly: false,
  supported: true,
  format: "mp3",
};

/**
 * @typedef {Object} TreeItem
 * @property {string} name
 * @property {string} path
 * @property {string} type
 * @property {string} [file_type]
 * @property {number} [size]
 * @property {TreeItem[]} [children]
 */

/**
 * @returns {TreeItem[]}
 */
function makeTree() {
  return [
    {
      name: "Albums",
      path: "Albums",
      type: "directory",
      children: [
        {
          name: "cover.jpg",
          path: "Albums/cover.jpg",
          type: "file",
          file_type: "image",
          size: 12,
        },
        {
          name: "notes.txt",
          path: "Albums/notes.txt",
          type: "file",
          file_type: "text",
          size: 5,
        },
        {
          name: "readme.pdf",
          path: "Albums/readme.pdf",
          type: "file",
          file_type: "other",
          size: 8,
        },
        {
          name: "song.mp3",
          path: "Albums/song.mp3",
          type: "file",
          file_type: "audio",
          size: 20,
        },
      ],
    },
    {
      name: "loose.flac",
      path: "loose.flac",
      type: "file",
      file_type: "audio",
      size: 30,
    },
  ];
}

/**
 * @param {unknown} body
 * @param {{ status?: number, contentType?: string }} [options]
 */
function makeResponse(
  body,
  { status = 200, contentType = "application/json" } = {},
) {
  const text =
    typeof body === "string"
      ? body
      : body instanceof Blob
        ? ""
        : JSON.stringify(body);
  /** @type {Record<string, string>} */
  const headers = { "content-type": contentType };

  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? "OK" : "Error",
    headers: {
      /** @param {string} name */
      get: (name) => headers[name.toLowerCase()] ?? null,
    },
    json: async () => body,
    text: async () => text,
    blob: async () =>
      body instanceof Blob ? body : new Blob([text], { type: contentType }),
  };
}

/**
 * @param {string | URL | Request} input
 * @returns {string}
 */
function urlOf(input) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** @type {ReturnType<typeof vi.fn>} */
let fetchMock;
/** @type {() => unknown} */
let filesReply;
/** @type {Record<string, unknown>} */
let apiOverrides;

/**
 * @param {string} url
 */
function callsTo(url) {
  return fetchMock.mock.calls.filter(([input]) => urlOf(input) === url);
}

/**
 * @param {string} prefix
 */
function callsStartingWith(prefix) {
  return fetchMock.mock.calls.filter(([input]) =>
    urlOf(input).startsWith(prefix),
  );
}

function stubApi() {
  fetchMock = vi.fn((/** @type {string | URL | Request} */ input) => {
    const url = urlOf(input);

    if (apiOverrides[url]) return Promise.resolve(apiOverrides[url]);
    if (url === "/api/files") return Promise.resolve(filesReply());
    if (url === "/api/addons") {
      return Promise.resolve(makeResponse({ fetchers: [] }));
    }
    if (url.startsWith("/api/logs?")) {
      return Promise.resolve(makeResponse({ logs: [] }));
    }
    if (url.startsWith("/api/version")) {
      return Promise.resolve(
        makeResponse({
          current_version: "v1.1.0",
          git_sha: "abc1234",
          update_available: false,
          max_upload_bytes: 1000,
        }),
      );
    }
    if (url.startsWith("/api/metadata?")) {
      return Promise.resolve(makeResponse(metadata));
    }
    if (url.startsWith("/api/audio?")) {
      return Promise.resolve(
        makeResponse(new Blob(["audio"], { type: "audio/mpeg" }), {
          contentType: "audio/mpeg",
        }),
      );
    }
    if (url.startsWith("/api/image?")) {
      return Promise.resolve(
        makeResponse(new Blob(["image"], { type: "image/png" }), {
          contentType: "image/png",
        }),
      );
    }
    if (url.startsWith("/api/text?")) {
      return Promise.resolve(makeResponse({ content: "line one" }));
    }
    if (url === "/api/mkdir") {
      return Promise.resolve(makeResponse({ path: "New Folder" }));
    }
    if (url === "/api/delete") {
      return Promise.resolve(makeResponse({ success: true }));
    }
    if (url === "/api/move") {
      return Promise.resolve(makeResponse({ success: true }));
    }

    return Promise.resolve(
      makeResponse({ error: "Not found" }, { status: 404 }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
}

/**
 * @param {import("@testing-library/svelte").RenderResult<typeof App>} view
 * @param {string} path
 * @returns {HTMLElement}
 */
function node(view, path) {
  const element =
    view.container.querySelector(`[data-file-path="${path}"]`) ??
    view.container.querySelector(`[data-folder-path="${path}"]`);

  if (!element) throw new Error(`Missing tree node: ${path}`);

  return /** @type {HTMLElement} */ (element);
}

async function renderAuthenticated() {
  const view = render(App);
  await waitFor(() => expect(callsTo("/api/files")).toHaveLength(1));
  await waitFor(() =>
    expect(view.container.querySelector(".file-tree-container")).toBeTruthy(),
  );
  return view;
}

describe("App", () => {
  beforeEach(() => {
    settings.set(structuredClone(initialSettings));
    toast.clear();
    dismiss();
    renamingPath.set(null);
    authToken.set(null);
    tokenExpiry.set(null);
    isAuthenticated.set(false);
    localStorage.clear();
    theme.set("light");
    vi.clearAllMocks();
    startDropMock.mockResolvedValue(undefined);
    filesReply = () => makeResponse(makeTree());
    apiOverrides = {};
    stubApi();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.className = "";
    document.querySelector('link[rel="icon"][type="image/svg+xml"]')?.remove();
  });

  it("shows the login screen when unauthenticated", () => {
    render(App);

    expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
    expect(screen.getByLabelText("Username")).toBeTruthy();
    expect(screen.queryByText("File Browser")).toBeNull();
  });

  it("loads and renders the tree after authentication", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    expect(screen.getByText("File Browser")).toBeTruthy();
    expect(node(view, "Albums")).toBeTruthy();
    expect(node(view, "loose.flac")).toBeTruthy();
    expect(screen.queryByText("No music files found")).toBeNull();
  });

  it("scrolls the file tree with the wheel while an item is dragged", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    // The scroll container is the panel itself; .file-tree-container has no
    // overflow.
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".file-tree-panel")
    );
    let scrollTop = 0;
    Object.defineProperty(container, "scrollTop", {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value;
      },
    });
    Object.defineProperty(container, "clientHeight", {
      configurable: true,
      value: 400,
    });
    Object.defineProperty(container, "scrollHeight", {
      configurable: true,
      value: 1200,
    });

    // Without a drag the page keeps its normal scrolling behaviour.
    await fireEvent.wheel(container, { deltaY: 120 });
    expect(container.scrollTop).toBe(0);

    // Internal moves are pointer-driven so the browser never enters a native
    // drag session (Firefox drops wheel events for the whole session).
    await fireEvent.pointerDown(node(view, "loose.flac"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 20,
      clientY: 30,
    });
    expect(document.querySelector(".tree-drag-ghost")).not.toBeNull();

    // The wheel can be dispatched at any element while the item is held; the
    // window-level handler takes over and scrolls the tree.
    await fireEvent.wheel(window, { deltaY: 120 });
    expect(container.scrollTop).toBe(120);

    await fireEvent.wheel(container, { deltaY: 60 });
    expect(container.scrollTop).toBe(180);

    await fireEvent.pointerUp(container, {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 30,
    });
    expect(document.querySelector(".tree-drag-ghost")).toBeNull();
    await fireEvent.wheel(window, { deltaY: 40 });

    expect(container.scrollTop).toBe(180);
  });

  it("moves a tree item onto a folder with a pointer drag", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.pointerDown(node(view, "loose.flac"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 30,
    });
    await fireEvent.pointerMove(node(view, "Albums"), {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 60,
      clientY: 60,
    });
    await fireEvent.pointerUp(node(view, "Albums"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 60,
      clientY: 60,
    });

    await waitFor(() => expect(callsTo("/api/move")).toHaveLength(1));
    expect(callsTo("/api/move")[0][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ source: "loose.flac", destination: "Albums" }),
    });
  });

  it("warns instead of moving when an item is dropped on itself", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const file = node(view, "loose.flac");

    await fireEvent.pointerDown(file, {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 30,
    });
    await fireEvent.pointerMove(file, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerUp(file, {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });

    expect(
      await screen.findByText("Cannot move an item into itself"),
    ).toBeTruthy();
    expect(callsTo("/api/move")).toHaveLength(0);
  });

  it("moves an item to the root when dropped on the File Browser header", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    await fireEvent.click(node(view, "Albums"));
    const song = await waitFor(() => node(view, "Albums/song.mp3"));
    const header = /** @type {HTMLElement} */ (
      view.container.querySelector(".panel-header")
    );

    await fireEvent.pointerDown(song, {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 40,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 50,
    });
    await fireEvent.pointerMove(header, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 60,
      clientY: 10,
    });
    await fireEvent.pointerUp(header, {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 60,
      clientY: 10,
    });

    await waitFor(() => expect(callsTo("/api/move")).toHaveLength(1));
    expect(callsTo("/api/move")[0][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ source: "Albums/song.mp3", destination: "" }),
    });
  });

  it("auto-scrolls the tree when a dragged item nears the bottom edge", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".file-tree-panel")
    );
    let scrollTop = 200;
    Object.defineProperty(container, "scrollTop", {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value;
      },
    });
    Object.defineProperty(container, "clientHeight", {
      configurable: true,
      value: 400,
    });
    Object.defineProperty(container, "scrollHeight", {
      configurable: true,
      value: 1200,
    });
    Object.defineProperty(container, "getBoundingClientRect", {
      configurable: true,
      value: () => ({
        top: 0,
        bottom: 400,
        left: 0,
        right: 300,
        width: 300,
        height: 400,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    });

    await fireEvent.pointerDown(node(view, "loose.flac"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 30,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 395,
    });

    await waitFor(() => expect(container.scrollTop).toBeGreaterThan(200));

    await fireEvent.pointerUp(window, {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 30,
      clientY: 395,
    });
  });

  it("leaves the wheel alone when the tree cannot scroll", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".file-tree-panel")
    );
    Object.defineProperty(container, "clientHeight", {
      configurable: true,
      value: 400,
    });
    Object.defineProperty(container, "scrollHeight", {
      configurable: true,
      value: 400,
    });

    await fireEvent.pointerDown(node(view, "loose.flac"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 20,
      clientY: 30,
    });
    const wheel = new WheelEvent("wheel", {
      deltaY: 120,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(wheel);

    expect(wheel.defaultPrevented).toBe(false);
  });

  it("shows an empty library state", async () => {
    isAuthenticated.set(true);
    filesReply = () => makeResponse([]);

    render(App);

    expect(await screen.findByText("No music files found")).toBeTruthy();
    expect(callsTo("/api/files")).toHaveLength(1);

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(callsTo("/api/files")).toHaveLength(1);
  });

  it("reports a tree load failure and retries", async () => {
    isAuthenticated.set(true);
    let attempts = 0;
    filesReply = () => {
      attempts += 1;
      return attempts === 1
        ? makeResponse("Library unavailable", {
            status: 500,
            contentType: "text/plain",
          })
        : makeResponse(makeTree());
    };

    const view = render(App);

    expect(await screen.findByText("Failed to load files")).toBeTruthy();
    expect(screen.getByText("Library unavailable")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(node(view, "loose.flac")).toBeTruthy());
    expect(callsTo("/api/files")).toHaveLength(2);
  });

  it("filters the tree by search and clears it", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const search = /** @type {HTMLInputElement} */ (
      screen.getByPlaceholderText("Search files...")
    );

    await fireEvent.input(search, { target: { value: "loose" } });

    await waitFor(() => expect(node(view, "loose.flac")).toBeTruthy());
    expect(
      view.container.querySelector('[data-folder-path="Albums"]'),
    ).toBeNull();

    await fireEvent.click(screen.getByTitle("Clear search"));

    await waitFor(() => expect(node(view, "Albums")).toBeTruthy());
    expect(search.value).toBe("");
  });

  it("clears the search with Escape", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();
    const search = /** @type {HTMLInputElement} */ (
      screen.getByPlaceholderText("Search files...")
    );

    await fireEvent.input(search, { target: { value: "loose" } });
    await fireEvent.keyDown(search, { key: "Escape" });

    await waitFor(() => expect(search.value).toBe(""));
  });

  it("routes selected files to the metadata, image and text viewers", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await fireEvent.click(node(view, "Albums/song.mp3"));

    expect(
      await screen.findByRole("heading", { name: "Metadata Editor" }),
    ).toBeTruthy();
    expect(await screen.findByDisplayValue("Song")).toBeTruthy();
    expect(callsStartingWith("/api/audio?path=Albums%2Fsong.mp3")).toHaveLength(
      1,
    );

    await fireEvent.click(node(view, "Albums/cover.jpg"));

    expect(
      await screen.findByRole("heading", { name: "Image Viewer" }),
    ).toBeTruthy();
    expect(await screen.findByRole("img", { name: "cover.jpg" })).toBeTruthy();

    await fireEvent.click(node(view, "Albums/notes.txt"));

    expect(
      await screen.findByRole("heading", { name: "Text Editor" }),
    ).toBeTruthy();
    expect(await screen.findByDisplayValue("line one")).toBeTruthy();
  });

  it("routes an unsupported file to the read-only editor", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await fireEvent.click(node(view, "Albums/readme.pdf"));

    expect(
      await screen.findByRole("heading", { name: "File Info (read-only)" }),
    ).toBeTruthy();
    expect(await screen.findByDisplayValue("Song")).toBeTruthy();
  });

  it("opens the folder overview for a selected folder", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));

    expect(
      await screen.findByRole("heading", { name: "Folder Overview" }),
    ).toBeTruthy();
    expect(
      screen.queryByText("All files have selected metadata fields"),
    ).toBeNull();

    await fireEvent.click(screen.getByTitle("Toggle folder metadata overview"));

    expect(
      await screen.findByText("All files have selected metadata fields"),
    ).toBeTruthy();
  });

  it("creates a root folder and refreshes the tree", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    await fireEvent.click(screen.getByRole("button", { name: "New Folder" }));

    await waitFor(() => expect(callsTo("/api/mkdir")).toHaveLength(1));
    expect(callsTo("/api/mkdir")[0][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ path: "New Folder" }),
    });
    expect(await screen.findByText("Folder created: New Folder")).toBeTruthy();
    expect(callsTo("/api/files")).toHaveLength(2);
  });

  it("renames and deletes the selected item with the keyboard", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "loose.flac"));
    await screen.findByRole("heading", { name: "Metadata Editor" });

    await fireEvent.keyDown(window, { key: "F2" });
    expect(get(renamingPath)).toBe("loose.flac");

    renamingPath.set(null);
    await fireEvent.keyDown(window, { key: "Delete" });

    await waitFor(() => expect(callsTo("/api/delete")).toHaveLength(1));
    expect(callsTo("/api/delete")[0][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ path: "loose.flac" }),
    });
  });

  it("ignores Delete when the setting is off", async () => {
    isAuthenticated.set(true);
    settings.update((current) => ({ ...current, allowDeleteKey: false }));
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "loose.flac"));
    await screen.findByRole("heading", { name: "Metadata Editor" });
    await fireEvent.keyDown(window, { key: "Delete" });

    expect(callsTo("/api/delete")).toHaveLength(0);
  });

  it("refreshes the tree on the refreshFileTree event", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    window.dispatchEvent(new Event("refreshFileTree"));

    await waitFor(() => expect(callsTo("/api/files")).toHaveLength(2));
  });

  it("uploads dropped files to the hovered folder", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const file = new File(["audio"], "new.mp3", { type: "audio/mpeg" });

    await fireEvent.drop(node(view, "Albums"), {
      dataTransfer: {
        types: ["Files"],
        items: [],
        files: [file],
        getData: () => "",
      },
    });

    await waitFor(() => expect(startDropMock).toHaveBeenCalledTimes(1));
    expect(startDropMock).toHaveBeenCalledWith(
      expect.objectContaining({
        files: [file],
        targetPath: "Albums",
        existing: expect.any(Map),
        conflict: "skip-identical",
        onComplete: expect.any(Function),
      }),
    );
  });

  it("uploads a picked folder into the selected folder", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const file = new File(["audio"], "picked.mp3", { type: "audio/mpeg" });

    await fireEvent.click(node(view, "Albums"));
    const input = /** @type {HTMLInputElement} */ (
      view.container.querySelector('input[type="file"]')
    );
    await fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(startDropMock).toHaveBeenCalledTimes(1));
    expect(startDropMock).toHaveBeenCalledWith(
      expect.objectContaining({ files: [file], targetPath: "Albums" }),
    );
  });

  it("logs out and returns to the login screen", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    await fireEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(await screen.findByRole("heading", { name: "Login" })).toBeTruthy();
    expect(get(isAuthenticated)).toBe(false);
    expect(screen.queryByText("File Browser")).toBeNull();
  });

  it("loads the tree again after logging out and back in", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    await fireEvent.click(screen.getByRole("button", { name: "Logout" }));
    await screen.findByRole("heading", { name: "Login" });

    await act(() => {
      isAuthenticated.set(true);
    });

    await waitFor(() => expect(callsTo("/api/files")).toHaveLength(2));
  });

  it("shows the upload progress bar", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    upload.set({
      ...get(upload),
      phase: "running",
      totalBytes: 100,
      doneBytes: 25,
    });

    await waitFor(() =>
      expect(view.container.querySelector(".upload-progress-bar")).toBeTruthy(),
    );
    expect(
      /** @type {HTMLElement} */ (
        view.container.querySelector(".upload-progress-bar")
      ).style.width,
    ).toBe("25%");
  });

  it("does not load audio when the player is disabled", async () => {
    isAuthenticated.set(true);
    settings.update((current) => ({ ...current, enablePlayer: false }));
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "loose.flac"));
    await screen.findByRole("heading", { name: "Metadata Editor" });

    expect(callsStartingWith("/api/audio?")).toHaveLength(0);
  });

  it("logs out when the API answers 401", async () => {
    isAuthenticated.set(true);
    filesReply = () => makeResponse({ error: "expired" }, { status: 401 });

    render(App);

    expect(await screen.findByRole("heading", { name: "Login" })).toBeTruthy();
    expect(get(isAuthenticated)).toBe(false);
  });

  it("rejects a file tree response that is not JSON", async () => {
    isAuthenticated.set(true);
    filesReply = () =>
      makeResponse("plain text", { contentType: "text/plain" });

    render(App);

    expect(await screen.findByText("Failed to load files")).toBeTruthy();
    expect(
      screen.getByText("Expected a JSON response but received text/plain"),
    ).toBeTruthy();
  });

  it("renames the selected file and reloads the tree", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/rename"] = makeResponse({
      success: true,
      newPath: "renamed.flac",
    });
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "loose.flac"));
    await screen.findByRole("heading", { name: "Metadata Editor" });
    await fireEvent.keyDown(window, { key: "F2" });

    const input = screen.getByDisplayValue("loose.flac");
    await fireEvent.input(input, { target: { value: "renamed.flac" } });
    await fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(callsTo("/api/rename")).toHaveLength(1));
    expect(callsTo("/api/rename")[0][1]).toMatchObject({
      body: JSON.stringify({ oldPath: "loose.flac", newName: "renamed.flac" }),
    });
    expect(await screen.findByText("Renamed successfully")).toBeTruthy();
    expect(callsTo("/api/files")).toHaveLength(2);
  });

  it("reports a rename failure", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/rename"] = makeResponse(
      { error: "name taken" },
      { status: 500 },
    );
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "loose.flac"));
    await screen.findByRole("heading", { name: "Metadata Editor" });
    await fireEvent.keyDown(window, { key: "F2" });
    const input = screen.getByDisplayValue("loose.flac");
    await fireEvent.input(input, { target: { value: "taken.flac" } });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByText("Rename failed: name taken")).toBeTruthy();
  });

  it("deletes a folder from the keyboard", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await screen.findByRole("heading", { name: "Folder Overview" });
    await fireEvent.keyDown(window, { key: "Delete" });

    await waitFor(() => expect(callsTo("/api/delete")).toHaveLength(1));
    expect(callsTo("/api/delete")[0][1]).toMatchObject({
      body: JSON.stringify({ path: "Albums" }),
    });
    expect(await screen.findByText("Deleted successfully")).toBeTruthy();
  });

  it("reports a delete failure", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/delete"] = makeResponse(
      { error: "locked" },
      { status: 500 },
    );
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "loose.flac"));
    await screen.findByRole("heading", { name: "Metadata Editor" });
    await fireEvent.keyDown(window, { key: "Delete" });

    expect(await screen.findByText("Delete failed: locked")).toBeTruthy();
  });

  it("reports a move failure after a tree drag", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/move"] = makeResponse(
      { error: "destination exists" },
      { status: 500 },
    );
    const view = await renderAuthenticated();

    await fireEvent.pointerDown(node(view, "loose.flac"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 30,
    });
    await fireEvent.pointerUp(node(view, "Albums"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 60,
      clientY: 60,
    });

    expect(
      await screen.findByText("Move failed: destination exists"),
    ).toBeTruthy();
  });

  it("cancels a pointer drag without moving anything", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();

    await fireEvent.pointerDown(node(view, "loose.flac"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 20,
      clientY: 20,
    });
    await fireEvent.pointerMove(window, {
      pointerId: 1,
      pointerType: "mouse",
      buttons: 1,
      clientX: 30,
      clientY: 30,
    });
    expect(document.querySelector(".tree-drag-ghost")).not.toBeNull();

    await fireEvent.pointerCancel(window, { pointerId: 1 });
    expect(document.querySelector(".tree-drag-ghost")).toBeNull();

    await fireEvent.pointerUp(node(view, "Albums"), {
      button: 0,
      pointerId: 1,
      pointerType: "mouse",
      clientX: 60,
      clientY: 60,
    });

    expect(callsTo("/api/move")).toHaveLength(0);
  });

  it("copies a file from the context menu", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/copy"] = makeResponse({ success: true });
    const view = await renderAuthenticated();

    await fireEvent.contextMenu(node(view, "loose.flac"), {
      clientX: 10,
      clientY: 10,
    });
    await fireEvent.click(screen.getByText("Copy"));

    await waitFor(() => expect(callsTo("/api/copy")).toHaveLength(1));
    expect(callsTo("/api/copy")[0][1]).toMatchObject({
      body: JSON.stringify({ path: "loose.flac" }),
    });
    expect(await screen.findByText("Copied successfully")).toBeTruthy();
  });

  it("reports a copy failure", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/copy"] = makeResponse(
      { error: "no space" },
      { status: 500 },
    );
    const view = await renderAuthenticated();

    await fireEvent.contextMenu(node(view, "loose.flac"), {
      clientX: 10,
      clientY: 10,
    });
    await fireEvent.click(screen.getByText("Copy"));

    expect(await screen.findByText("Copy failed: no space")).toBeTruthy();
  });

  it("creates a folder inside the selected folder", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/mkdir"] = makeResponse({ path: "Albums/New Folder" });
    const view = await renderAuthenticated();

    await fireEvent.contextMenu(node(view, "Albums"), {
      clientX: 10,
      clientY: 10,
    });
    await fireEvent.click(screen.getByText("Create folder"));

    await waitFor(() => expect(callsTo("/api/mkdir")).toHaveLength(1));
    expect(callsTo("/api/mkdir")[0][1]).toMatchObject({
      body: JSON.stringify({ path: "Albums/New Folder" }),
    });
    expect(
      await screen.findByText("Folder created: Albums/New Folder"),
    ).toBeTruthy();
  });

  it("reports a folder creation failure", async () => {
    isAuthenticated.set(true);
    apiOverrides["/api/mkdir"] = makeResponse(
      { error: "access denied" },
      { status: 500 },
    );
    await renderAuthenticated();

    await fireEvent.click(screen.getByRole("button", { name: "New Folder" }));

    expect(
      await screen.findByText("Create folder failed: access denied"),
    ).toBeTruthy();
  });

  it("reports an audio load failure", async () => {
    isAuthenticated.set(true);
    vi.spyOn(console, "error").mockImplementation(() => {});
    apiOverrides["/api/audio?path=Albums%2Fsong.mp3"] = makeResponse(
      { error: "bad audio" },
      { status: 500 },
    );
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await fireEvent.click(node(view, "Albums/song.mp3"));

    expect(
      await screen.findByText("Failed to load audio file: bad audio"),
    ).toBeTruthy();
  });

  it("rejects an audio response with the wrong content type", async () => {
    isAuthenticated.set(true);
    vi.spyOn(console, "error").mockImplementation(() => {});
    apiOverrides["/api/audio?path=Albums%2Fsong.mp3"] = makeResponse(
      "not audio",
      { contentType: "text/plain" },
    );
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await fireEvent.click(node(view, "Albums/song.mp3"));

    expect(
      await screen.findByText(
        "Failed to load audio file: Expected an audio file but received text/plain",
      ),
    ).toBeTruthy();
  });

  it("reports a failed upload started by a drop", async () => {
    isAuthenticated.set(true);
    vi.spyOn(console, "error").mockImplementation(() => {});
    startDropMock.mockRejectedValueOnce(new Error("disk full"));
    const view = await renderAuthenticated();
    const file = new File(["audio"], "new.mp3", { type: "audio/mpeg" });

    await fireEvent.drop(node(view, "Albums"), {
      dataTransfer: {
        types: ["Files"],
        items: [],
        files: [file],
        getData: () => "",
      },
    });

    expect(await screen.findByText("Upload failed: disk full")).toBeTruthy();
  });

  it("reports a failed upload from the folder picker", async () => {
    isAuthenticated.set(true);
    vi.spyOn(console, "error").mockImplementation(() => {});
    startDropMock.mockRejectedValueOnce(new Error("offline"));
    const view = await renderAuthenticated();
    await fireEvent.click(node(view, "Albums"));
    const input = /** @type {HTMLInputElement} */ (
      view.container.querySelector('input[type="file"]')
    );
    const file = new File(["audio"], "picked.mp3", { type: "audio/mpeg" });

    await fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText("Upload failed: offline")).toBeTruthy();
  });

  it("ignores an empty folder picker selection", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const input = /** @type {HTMLInputElement} */ (
      view.container.querySelector('input[type="file"]')
    );

    await fireEvent.change(input, { target: { files: [] } });

    expect(startDropMock).not.toHaveBeenCalled();
  });

  it("opens the settings, help and log modals", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    await fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(
      await screen.findByRole("heading", { name: "Settings" }),
    ).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Help" }));
    expect(
      await screen.findByRole("heading", { name: "Help & Information" }),
    ).toBeTruthy();

    window.dispatchEvent(new Event("openLogs"));
    expect(
      await screen.findByRole("heading", { name: "Application Logs" }),
    ).toBeTruthy();
  });

  it("toggles the theme from the header", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    expect(get(theme)).toBe("light");
    await fireEvent.click(screen.getByRole("button", { name: "Light" }));

    await waitFor(() => expect(get(theme)).toBe("dark"));
    expect(screen.getByRole("button", { name: "Dark" })).toBeTruthy();
    expect(document.body.classList.contains("dark")).toBe(true);
  });

  it("resizes the panels with the split handle", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".split-container")
    );
    Object.defineProperty(container, "getBoundingClientRect", {
      configurable: true,
      value: () => ({
        left: 0,
        top: 0,
        right: 1000,
        bottom: 600,
        width: 1000,
        height: 600,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    });
    const resizer = /** @type {HTMLElement} */ (
      view.container.querySelector(".resizer")
    );
    const leftPanel = /** @type {HTMLElement} */ (
      view.container.querySelector(".left-panel")
    );

    await fireEvent.mouseDown(resizer);
    expect(document.body.classList.contains("resizing")).toBe(true);

    await fireEvent.mouseMove(document, { clientX: 300 });
    expect(parseFloat(leftPanel.style.width)).toBeCloseTo(30);

    await fireEvent.mouseMove(document, { clientX: 990 });
    expect(parseFloat(leftPanel.style.width)).toBeCloseTo(80);

    await fireEvent.mouseUp(document);
    expect(document.body.classList.contains("resizing")).toBe(false);
  });

  it("warns before unloading the page while uploading", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    upload.set({
      ...get(upload),
      phase: "running",
      totalBytes: 100,
      doneBytes: 20,
    });
    await waitFor(() =>
      expect(view.container.querySelector(".upload-progress-bar")).toBeTruthy(),
    );

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });

  it("does not block unloading when no upload is running", async () => {
    isAuthenticated.set(true);
    await renderAuthenticated();

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });

  it("ends an external drag on blur and Escape", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".container")
    );

    await fireEvent.dragEnter(container, {
      dataTransfer: { types: ["Files"] },
    });
    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(true),
    );

    window.dispatchEvent(new Event("blur"));

    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(false),
    );

    await fireEvent.dragEnter(container, {
      dataTransfer: { types: ["Files"] },
    });
    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(true),
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(false),
    );
  });

  it("keeps the drop overlay while the pointer is inside the window", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".container")
    );

    await fireEvent.dragEnter(container, {
      dataTransfer: { types: ["Files"] },
    });
    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(true),
    );

    const leave = (/** @type {number} */ x, /** @type {number} */ y) => {
      const event = new Event("dragleave", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "clientX", { value: x });
      Object.defineProperty(event, "clientY", { value: y });
      container.dispatchEvent(event);
    };

    leave(100, 100);
    expect(container.classList.contains("dragging")).toBe(true);

    leave(window.innerWidth + 10, window.innerHeight + 10);
    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(false),
    );
  });

  it("accepts a legacy DOMStringList in the drag types", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".container")
    );
    const event = new Event("dragenter", {
      bubbles: true,
      cancelable: true,
    });
    Object.defineProperty(event, "dataTransfer", {
      value: {
        types: { contains: (/** @type {string} */ type) => type === "Files" },
      },
    });

    container.dispatchEvent(event);

    await waitFor(() =>
      expect(container.classList.contains("dragging")).toBe(true),
    );
  });

  it("ignores a drag that started from a text field", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".container")
    );
    const search = screen.getByPlaceholderText("Search files...");

    await fireEvent.dragStart(search);
    await fireEvent.dragEnter(container, {
      dataTransfer: { types: ["Files"] },
    });

    expect(container.classList.contains("dragging")).toBe(false);

    await fireEvent.dragEnd(search);
  });

  it("uses the parent folder when files are dropped on a file row", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const file = new File(["audio"], "new.mp3", { type: "audio/mpeg" });

    await fireEvent.drop(node(view, "loose.flac"), {
      dataTransfer: {
        types: ["Files"],
        items: [],
        files: [file],
        getData: () => "",
      },
    });

    await waitFor(() => expect(startDropMock).toHaveBeenCalledTimes(1));
    expect(startDropMock).toHaveBeenCalledWith(
      expect.objectContaining({ targetPath: "" }),
    );
  });

  it("ignores a drop without files", async () => {
    isAuthenticated.set(true);
    const view = await renderAuthenticated();
    const container = /** @type {HTMLElement} */ (
      view.container.querySelector(".container")
    );

    await fireEvent.drop(container, {
      dataTransfer: { types: ["Files"], items: [], files: [] },
    });

    expect(startDropMock).not.toHaveBeenCalled();
  });

  it("includes nested audio in the recursive folder overview", async () => {
    isAuthenticated.set(true);
    settings.update((current) => ({ ...current, recursiveOverview: true }));
    filesReply = () =>
      makeResponse([
        {
          name: "Albums",
          path: "Albums",
          type: "directory",
          children: [
            {
              name: "song.mp3",
              path: "Albums/song.mp3",
              type: "file",
              file_type: "audio",
              size: 20,
            },
            {
              name: "CD2",
              path: "Albums/CD2",
              type: "directory",
              children: [
                {
                  name: "deep.flac",
                  path: "Albums/CD2/deep.flac",
                  type: "file",
                  file_type: "audio",
                  size: 20,
                },
              ],
            },
          ],
        },
      ]);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await fireEvent.click(screen.getByTitle("Toggle folder metadata overview"));

    await waitFor(() =>
      expect(callsStartingWith("/api/metadata?path=")).toHaveLength(2),
    );
    expect(
      callsStartingWith("/api/metadata?path=Albums%2FCD2%2Fdeep.flac"),
    ).toHaveLength(1);
  });

  it("only checks direct children without recursive overview", async () => {
    isAuthenticated.set(true);
    filesReply = () =>
      makeResponse([
        {
          name: "Albums",
          path: "Albums",
          type: "directory",
          children: [
            {
              name: "song.mp3",
              path: "Albums/song.mp3",
              type: "file",
              file_type: "audio",
              size: 20,
            },
            {
              name: "CD2",
              path: "Albums/CD2",
              type: "directory",
              children: [
                {
                  name: "deep.flac",
                  path: "Albums/CD2/deep.flac",
                  type: "file",
                  file_type: "audio",
                  size: 20,
                },
              ],
            },
          ],
        },
      ]);
    const view = await renderAuthenticated();

    await fireEvent.click(node(view, "Albums"));
    await fireEvent.click(screen.getByTitle("Toggle folder metadata overview"));

    await waitFor(() =>
      expect(callsStartingWith("/api/metadata?path=")).toHaveLength(1),
    );
    expect(
      callsStartingWith("/api/metadata?path=Albums%2FCD2%2Fdeep.flac"),
    ).toHaveLength(0);
  });
});
