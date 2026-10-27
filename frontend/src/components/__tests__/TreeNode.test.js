import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";
import { get } from "svelte/store";

import TreeNode from "../TreeNode.svelte";
import { contextMenu, renamingPath } from "../../stores/context.store.js";
import { settings } from "../../utils/settings.utils.js";
import { toast } from "../../stores/toast.store.js";

/**
 * @typedef {Object} TreeItem
 * @property {string} name
 * @property {string} path
 * @property {string} type
 * @property {string} [file_type]
 * @property {number} [size]
 * @property {TreeItem[]} [children]
 */

/** @type {TreeItem} */
const audioItem = {
  name: "song.mp3",
  path: "folder/song.mp3",
  type: "file",
  file_type: "audio",
  size: 2048,
};

/** @type {TreeItem} */
const imageItem = {
  name: "cover.jpg",
  path: "folder/cover.jpg",
  type: "file",
  file_type: "image",
  size: 1024,
};

/** @type {TreeItem} */
const folderItem = {
  name: "folder",
  path: "folder",
  type: "directory",
  children: [audioItem, imageItem],
};

/** @type {TreeItem} */
const textItem = {
  name: "lyrics.lrc",
  path: "folder/lyrics.lrc",
  type: "file",
  file_type: "text",
  size: 512,
};

/** @type {TreeItem} */
const otherItem = {
  name: "notes.pdf",
  path: "folder/notes.pdf",
  type: "file",
  file_type: "other",
  size: 4096,
};

/** @type {TreeItem} */
const rootAudioItem = {
  name: "song.mp3",
  path: "song.mp3",
  type: "file",
  file_type: "audio",
  size: 2048,
};

/**
 * @param {number} status
 * @param {unknown} body
 */
function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

/**
 * @param {TreeItem} item
 * @param {Record<string, unknown>} [overrides]
 */
function setup(item, overrides = {}) {
  const handlers = {
    toggleDir: vi.fn(),
    selectFile: vi.fn(),
    selectFolder: vi.fn(),
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onCreateFolder: vi.fn(),
    onCopy: vi.fn(),
  };
  const result = render(TreeNode, {
    props: {
      item,
      expanded: { has: () => false },
      ...handlers,
      selectedFolder: null,
      selectedFile: null,
      level: 0,
      ...overrides,
    },
  });
  return { ...result, ...handlers };
}

/**
 * @param {string} name
 */
async function openMenu(name) {
  await fireEvent.contextMenu(screen.getByText(name), {
    clientX: 40,
    clientY: 60,
  });
  await tick();
}

describe("TreeNode", () => {
  /** @type {Record<string, any>} */
  let originalSettings;

  beforeEach(() => {
    originalSettings = get(settings);
    contextMenu.set({ isOpen: false, path: null, x: 0, y: 0, type: null });
    renamingPath.set(null);
  });

  afterEach(() => {
    settings.set(originalSettings);
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    toast.clear();
    contextMenu.set({ isOpen: false, path: null, x: 0, y: 0, type: null });
    renamingPath.set(null);
  });

  it("selects a file when clicked", async () => {
    const { selectFile, selectFolder } = setup(audioItem);

    await fireEvent.click(screen.getByText("song.mp3"));

    expect(selectFile).toHaveBeenCalledWith("folder/song.mp3");
    expect(selectFolder).not.toHaveBeenCalled();
  });

  it("opens and collapses a folder when clicked", async () => {
    const { selectFolder, toggleDir } = setup(folderItem);

    await fireEvent.click(screen.getByText("folder"));

    expect(selectFolder).toHaveBeenCalledWith("folder");
    expect(toggleDir).toHaveBeenCalledWith("folder");
  });

  it("opens the audio context menu with every action", async () => {
    setup(audioItem);

    await openMenu("song.mp3");

    expect(get(contextMenu)).toMatchObject({
      isOpen: true,
      path: "folder/song.mp3",
      type: "file",
    });
    expect(screen.getByText("Rename")).toBeTruthy();
    expect(screen.getByText("Smart Rename")).toBeTruthy();
    expect(screen.getByText("Fetch Song Metadata")).toBeTruthy();
    expect(screen.getByText("Copy")).toBeTruthy();
    expect(screen.getByText("Download")).toBeTruthy();
    expect(screen.getByText("Create folder")).toBeTruthy();
    expect(screen.getByText("Delete")).toBeTruthy();
  });

  it("uses the configured hold duration for delete", async () => {
    settings.set({ ...get(settings), holdDeleteDuration: 700 });
    const { onDelete } = setup(audioItem);
    await openMenu("song.mp3");

    vi.useFakeTimers();
    try {
      const deleteButton = screen.getByRole("button", { name: "Delete" });

      await fireEvent.mouseDown(deleteButton);
      await vi.advanceTimersByTimeAsync(600);
      expect(onDelete).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(100);
      expect(onDelete).toHaveBeenCalledWith("folder/song.mp3");
    } finally {
      vi.useRealTimers();
    }
  });

  it("hides audio-only actions for an image", async () => {
    setup(imageItem);

    await openMenu("cover.jpg");

    expect(screen.getByText("Rename")).toBeTruthy();
    expect(screen.queryByText("Smart Rename")).toBeNull();
    expect(screen.queryByText("Fetch Song Metadata")).toBeNull();
    expect(screen.queryByText("Fetch Album Metadata")).toBeNull();
  });

  it("offers the folder actions for a directory", async () => {
    setup(folderItem);

    await openMenu("folder");

    expect(screen.getByText("Smart Rename All Audio")).toBeTruthy();
    expect(screen.getByText("Fetch Album Metadata")).toBeTruthy();
    expect(screen.queryByText("Fetch Song Metadata")).toBeNull();
  });

  it("closes the menu on Escape", async () => {
    setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByText("Rename")).toBeNull();
    expect(get(contextMenu).isOpen).toBe(false);
  });

  it("passes the copy action the item path", async () => {
    const { onCopy } = setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Copy"));

    expect(onCopy).toHaveBeenCalledWith("folder/song.mp3");
  });

  it("creates a folder in the parent of a file", async () => {
    const { onCreateFolder } = setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Create folder"));

    expect(onCreateFolder).toHaveBeenCalledWith("folder");
    expect(screen.queryByText("Create folder")).toBeNull();
  });

  it("renames a file inline and submits on Enter", async () => {
    const { onRename } = setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Rename"));

    const input = await screen.findByRole("textbox");
    expect(/** @type {HTMLInputElement} */ (input).value).toBe("song.mp3");

    await fireEvent.input(input, { target: { value: "renamed.mp3" } });
    await tick();
    await fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(onRename).toHaveBeenCalledWith("folder/song.mp3", "renamed.mp3"),
    );
    expect(get(renamingPath)).toBeNull();
  });

  it("cancels an inline rename on Escape", async () => {
    setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Rename"));
    const input = await screen.findByRole("textbox");
    await fireEvent.keyDown(input, { key: "Escape" });

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(get(renamingPath)).toBeNull();
    expect(screen.getByText("song.mp3")).toBeTruthy();
  });

  it("submits a trimmed name when the rename input loses focus", async () => {
    const { onRename } = setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Rename"));
    const input = await screen.findByRole("textbox");
    await fireEvent.input(input, { target: { value: "  spaced.mp3  " } });
    await fireEvent.blur(input);

    await waitFor(() =>
      expect(onRename).toHaveBeenCalledWith("folder/song.mp3", "spaced.mp3"),
    );
    expect(get(renamingPath)).toBeNull();
  });

  it("ignores an empty rename and keeps editing", async () => {
    const { onRename } = setup(audioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Rename"));
    const input = await screen.findByRole("textbox");
    await fireEvent.input(input, { target: { value: "   " } });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(get(renamingPath)).toBe("folder/song.mp3");
  });

  it("marks the selected file and folder", () => {
    const fileRender = setup(audioItem, { selectedFile: "folder/song.mp3" });
    expect(
      fileRender.container
        .querySelector(".file")
        ?.classList.contains("selected"),
    ).toBe(true);

    fileRender.unmount();

    const folderRender = setup(folderItem, { selectedFolder: "folder" });
    expect(
      folderRender.container
        .querySelector(".directory")
        ?.classList.contains("selected"),
    ).toBe(true);
  });

  it("renders a badge for every file type", async () => {
    const audioRender = setup(audioItem);
    expect(screen.getByText("MP3")).toBeTruthy();
    audioRender.unmount();

    const imageRender = setup(imageItem);
    expect(screen.getByText("JPG").classList.contains("image-format")).toBe(
      true,
    );
    imageRender.unmount();

    const textRender = setup(textItem);
    expect(screen.getByText("LRC").classList.contains("text-format")).toBe(
      true,
    );
    textRender.unmount();

    setup(otherItem);
    expect(screen.getByText("PDF").classList.contains("other-format")).toBe(
      true,
    );
  });

  it("summarises an empty folder in its tooltip", () => {
    const { container } = setup({ ...folderItem, children: [] });

    expect(
      /** @type {HTMLElement} */ (container.querySelector(".directory")).title,
    ).toBe("Empty folder");
  });

  it("summarises folder contents in its tooltip", () => {
    const nested = {
      name: "nested",
      path: "folder/nested",
      type: "directory",
      children: [
        {
          name: "deep.flac",
          path: "folder/nested/deep.flac",
          type: "file",
          file_type: "audio",
          size: 1024,
        },
      ],
    };
    const { container } = setup({
      ...folderItem,
      children: [...(folderItem.children ?? []), nested],
    });

    expect(
      /** @type {HTMLElement} */ (container.querySelector(".directory")).title,
    ).toBe("4 KB\nfolders x1\nmp3 x1\njpg x1\nflac x1");
  });

  it("renders sorted children when the folder is expanded", () => {
    /** @type {TreeItem} */
    const item = {
      name: "folder",
      path: "folder",
      type: "directory",
      children: [
        {
          name: "b.mp3",
          path: "folder/b.mp3",
          type: "file",
          file_type: "audio",
        },
        { name: "zdir", path: "folder/zdir", type: "directory", children: [] },
        {
          name: "a.mp3",
          path: "folder/a.mp3",
          type: "file",
          file_type: "audio",
        },
        { name: "adir", path: "folder/adir", type: "directory", children: [] },
      ],
    };
    const { container } = setup(item, {
      expanded: { has: (/** @type {string} */ path) => path === "folder" },
    });

    const names = [...container.querySelectorAll(".name")].map(
      (node) => node.textContent,
    );
    expect(names).toEqual(["folder", "adir", "zdir", "a.mp3", "b.mp3"]);
  });

  it("closes the context menu when clicking outside it", async () => {
    setup(audioItem);
    await openMenu("song.mp3");
    await new Promise((resolve) => setTimeout(resolve, 0));

    await fireEvent.click(document.body);
    await tick();

    expect(get(contextMenu).isOpen).toBe(false);
    expect(screen.queryByText("Rename")).toBeNull();
  });

  it("keeps the context menu open when clicking inside it", async () => {
    setup(audioItem);
    await openMenu("song.mp3");
    await new Promise((resolve) => setTimeout(resolve, 0));

    const menu = /** @type {HTMLElement} */ (
      document.querySelector(".context-menu")
    );
    await fireEvent.click(menu);

    expect(get(contextMenu).isOpen).toBe(true);
    expect(screen.getByText("Rename")).toBeTruthy();
  });

  it("creates a folder in the library root from a top-level file", async () => {
    const { onCreateFolder } = setup(rootAudioItem);
    await openMenu("song.mp3");

    await fireEvent.click(screen.getByText("Create folder"));

    expect(onCreateFolder).toHaveBeenCalledWith("");
  });

  it("downloads a file using a short-lived token", async () => {
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    const infoSpy = vi.spyOn(toast, "info");
    const successSpy = vi.spyOn(toast, "success");
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse(200, { token: "download-token", filename: "song.mp3" }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    setup(audioItem);
    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Download"));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/download-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: "folder/song.mp3", isFolder: false }),
    });
    expect(infoSpy).toHaveBeenCalledWith("Preparing download: song.mp3", 15000);
    expect(successSpy).toHaveBeenCalledWith("Download started: song.mp3");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("downloads a folder with the archive fallback name", async () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const successSpy = vi.spyOn(toast, "success");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(200, { token: "zip-token" }))),
    );

    setup(folderItem);
    await openMenu("folder");
    await fireEvent.click(screen.getByText("Download"));

    await waitFor(() =>
      expect(successSpy).toHaveBeenCalledWith(
        "Download requested: folder.zip (preparing archive)",
      ),
    );
  });

  it("reports a failed download response", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(jsonResponse(500, { error: "download denied" })),
      ),
    );

    setup(audioItem);
    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Download"));

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith("Download failed: download denied"),
    );
  });

  it("reports a network failure while downloading", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline"))),
    );

    setup(audioItem);
    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Download"));

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith("Download failed: offline"),
    );
  });

  it("smart renames a file and follows the new path", async () => {
    const successSpy = vi.spyOn(toast, "success");
    const refreshHandler = vi.fn();
    window.addEventListener("refreshFileTree", refreshHandler);
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse(200, {
          success: true,
          newName: "Artist - Song.mp3",
          newPath: "folder/Artist - Song.mp3",
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { selectFile } = setup(audioItem);

    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Smart Rename"));

    await waitFor(() =>
      expect(selectFile).toHaveBeenCalledWith("folder/Artist - Song.mp3"),
    );
    expect(successSpy).toHaveBeenCalledWith(
      "Successfully renamed to: Artist - Song.mp3",
    );
    expect(refreshHandler).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/apply-renaming-scheme",
      expect.objectContaining({
        body: JSON.stringify({
          path: "folder/song.mp3",
          scheme: get(settings).fileScheme,
          isFolder: false,
          replaceSpaces: false,
        }),
      }),
    );
    window.removeEventListener("refreshFileTree", refreshHandler);
  });

  it("warns when no smart rename scheme is configured", async () => {
    settings.set({ ...get(settings), fileScheme: "  " });
    const warningSpy = vi.spyOn(toast, "warning");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    setup(audioItem);

    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Smart Rename"));

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith(
        "No file renaming scheme configured in settings",
      ),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports a failed smart rename", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(500, { error: "name taken" }))),
    );
    setup(audioItem);

    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Smart Rename"));

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith(
        "Smart rename failed: Failed to apply renaming scheme: name taken",
      ),
    );
  });

  it("smart renames every audio file in a folder", async () => {
    const successSpy = vi.spyOn(toast, "success");
    const refreshHandler = vi.fn();
    window.addEventListener("refreshFileTree", refreshHandler);
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse(200, { success: true, newName: "renamed", newPath: "x" }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    /** @type {TreeItem} */
    const folder = {
      name: "folder",
      path: "folder",
      type: "directory",
      children: [
        audioItem,
        { ...audioItem, name: "two.flac", path: "folder/two.flac" },
        imageItem,
      ],
    };
    setup(folder);

    await openMenu("folder");
    await fireEvent.click(screen.getByText("Smart Rename All Audio"));

    await waitFor(() =>
      expect(successSpy).toHaveBeenCalledWith(
        "Successfully renamed all 2 audio file(s)",
      ),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refreshHandler).toHaveBeenCalledTimes(1);
    window.removeEventListener("refreshFileTree", refreshHandler);
  });

  it("reports when a folder has no audio to smart rename", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    setup({ ...folderItem, children: [imageItem] });

    await openMenu("folder");
    await fireEvent.click(screen.getByText("Smart Rename All Audio"));

    await waitFor(() =>
      expect(infoSpy).toHaveBeenCalledWith(
        "No supported audio files found in this folder",
      ),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("counts smart rename failures for a folder", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const warningSpy = vi.spyOn(toast, "warning");
    const fetchMock = vi.fn(
      /** @param {string} url @param {RequestInit} options */
      (url, options) => {
        const body = JSON.parse(String(options.body));
        return Promise.resolve(
          body.path === "folder/song.mp3"
            ? jsonResponse(200, {
                success: true,
                newName: "renamed.mp3",
                newPath: "folder/renamed.mp3",
              })
            : jsonResponse(200, {
                success: false,
                error: "conflict",
              }),
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    /** @type {TreeItem} */
    const folder = {
      name: "folder",
      path: "folder",
      type: "directory",
      children: [
        audioItem,
        { ...audioItem, name: "two.mp3", path: "folder/two.mp3" },
      ],
    };
    setup(folder);

    await openMenu("folder");
    await fireEvent.click(screen.getByText("Smart Rename All Audio"));

    await waitFor(() =>
      expect(warningSpy).toHaveBeenCalledWith(
        "Renamed 1 of 2 audio file(s), 1 failed",
      ),
    );
  });

  it("opens the metadata fetcher for a song", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(200, []))),
    );
    setup(audioItem);

    await openMenu("song.mp3");
    await fireEvent.click(screen.getByText("Fetch Song Metadata"));

    expect(
      await screen.findByRole("heading", { name: "Fetch Song Metadata" }),
    ).toBeTruthy();
    expect(get(contextMenu).isOpen).toBe(false);
  });

  it("opens the metadata fetcher for a folder", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(200, []))),
    );
    setup(folderItem);

    await openMenu("folder");
    await fireEvent.click(screen.getByText("Fetch Album Metadata"));

    expect(
      await screen.findByRole("heading", {
        name: "Fetch Album Metadata (Folder Batch)",
      }),
    ).toBeTruthy();
  });
});
