import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import { contextMenu, renamingPath } from "../context.store.js";

describe("context store", () => {
  beforeEach(() => {
    contextMenu.set({ isOpen: false, path: null, x: 0, y: 0, type: null });
    renamingPath.set(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts closed with no target", () => {
    expect(get(contextMenu)).toEqual({
      isOpen: false,
      path: null,
      x: 0,
      y: 0,
      type: null,
    });
    expect(get(renamingPath)).toBeNull();
  });

  it("stores an open menu position and target", () => {
    contextMenu.set({
      isOpen: true,
      path: "folder/song.mp3",
      x: 120,
      y: 40,
      type: "file",
    });

    expect(get(contextMenu)).toEqual({
      isOpen: true,
      path: "folder/song.mp3",
      x: 120,
      y: 40,
      type: "file",
    });
  });

  it("stores the inline rename target", () => {
    renamingPath.set("folder");

    expect(get(renamingPath)).toBe("folder");

    renamingPath.set(null);

    expect(get(renamingPath)).toBeNull();
  });
});
