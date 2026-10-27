import { describe, expect, it } from "vitest";

import { formatFileSize, getFolderSummary } from "../folderSummary.utils.js";

/**
 * @typedef {Object} TestNode
 * @property {string} name
 * @property {string} type
 * @property {number} [size]
 * @property {TestNode[]} [children]
 */

/**
 * @param {string} name
 * @param {number} [size]
 * @returns {TestNode}
 */
function file(name, size = 0) {
  return { name, type: "file", size };
}

/**
 * @param {string} name
 * @param {TestNode[]} [children]
 * @returns {TestNode}
 */
function folder(name, children = []) {
  return { name, type: "directory", children };
}

describe("folderSummary", () => {
  it("returns null for missing or non-directory nodes", () => {
    expect(getFolderSummary()).toBeNull();
    expect(getFolderSummary(file("song.mp3"))).toBeNull();
  });

  it("returns zeroes for an empty folder", () => {
    expect(getFolderSummary(folder("empty"))).toEqual({
      folderCount: 0,
      fileCount: 0,
      totalSize: 0,
      formatCounts: {},
      totalItems: 0,
    });
  });

  it("counts files and folders recursively", () => {
    const tree = folder("root", [
      file("a.mp3", 100),
      file("b.flac", 250),
      folder("sub", [file("c.mp3", 50), folder("deeper", [file("d.jpg", 10)])]),
    ]);

    expect(getFolderSummary(tree)).toEqual({
      folderCount: 2,
      fileCount: 4,
      totalSize: 410,
      formatCounts: { MP3: 2, FLAC: 1, JPG: 1 },
      totalItems: 6,
    });
  });

  it("treats missing sizes as zero and counts extensionless files", () => {
    const tree = folder("root", [file("README"), file("track.mp3")]);

    const summary = getFolderSummary(tree);

    expect(summary?.totalSize).toBe(0);
    expect(summary?.formatCounts).toEqual({ unknown: 1, MP3: 1 });
  });

  it("formats byte sizes", () => {
    expect(formatFileSize(0)).toBe("0 B");
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(1024)).toBe("1 KB");
    expect(formatFileSize(1234)).toBe("1.21 KB");
    expect(formatFileSize(1024 * 1024)).toBe("1 MB");
    expect(formatFileSize(2.5 * 1024 * 1024 * 1024)).toBe("2.5 GB");
  });
});
