import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";
import { get } from "svelte/store";

import TreeNode from "../TreeNode.svelte";
import { contextMenu, renamingPath } from "../../stores/context.store.js";

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

/**
 * @param {TreeItem} item
 */
function setup(item) {
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
  beforeEach(() => {
    contextMenu.set({ isOpen: false, path: null, x: 0, y: 0, type: null });
    renamingPath.set(null);
  });

  afterEach(() => {
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
});
