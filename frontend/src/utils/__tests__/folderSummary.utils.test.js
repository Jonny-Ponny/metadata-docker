import { describe, expect, it } from "vitest";

import {
  formatFileSize,
  formatFolderSummary,
  getFolderSummary,
  MAX_FORMAT_LINES,
} from "../folderSummary.utils.js";

/**
 * @param {string} name
 * @param {number} [size]
 * @param {string} [type]
 */
function file(name, size = 0, type = "file") {
  return { name, size, type };
}

/**
 * @param {string} name
 * @param {any[]} [children]
 * @param {Record<string, unknown>} [extra]
 */
function folder(name, children = [], extra = {}) {
  return { name, type: "directory", children, ...extra };
}

describe("getFolderSummary", () => {
  it("returns null for a non-folder", () => {
    expect(getFolderSummary()).toBeNull();
    expect(getFolderSummary(file("song.mp3"))).toBeNull();
  });

  it("recursively counts files, folders and sizes", () => {
    const tree = folder("album", [
      file("a.mp3", 10),
      folder("disc", [file("b.flac", 20)]),
    ]);

    expect(getFolderSummary(tree)).toEqual({
      folderCount: 1,
      fileCount: 2,
      totalSize: 30,
      formatCounts: { MP3: 1, FLAC: 1 },
      totalItems: 3,
    });
  });

  it("uses the direct-child counts when the node carries them", () => {
    const node = folder("album", [folder("disc", [file("b.flac", 20)])], {
      folder_count: 1,
      file_count: 2,
      file_size: 30,
    });

    expect(getFolderSummary(node)).toEqual({
      folderCount: 1,
      fileCount: 2,
      totalSize: 30,
      formatCounts: {},
      totalItems: 3,
    });
  });
});

describe("formatFolderSummary", () => {
  it("uses the direct-child counts returned with a listing", () => {
    const text = formatFolderSummary({
      children: null,
      folder_count: 2,
      file_count: 3,
      file_size: 1024,
    });

    expect(text).toBe("1 KB\nfolders x2");
  });

  it("counts formats from the listed children and sorts them", () => {
    const text = formatFolderSummary({
      children: [
        { name: "a.mp3", type: "file", size: 2048 },
        { name: "b.mp3", type: "file", size: 2048 },
        { name: "c.flac", type: "file", size: 0 },
      ],
    });

    expect(text).toBe("4 KB\nmp3 x2\nflac x1");
  });

  it("says a folder is empty", () => {
    expect(
      formatFolderSummary({ children: [], folder_count: 0, file_count: 0 }),
    ).toBe("Empty folder");
  });

  it("does not walk nested folders when counts are already known", () => {
    // The nested children are deliberately wrong; the counts must win.
    const text = formatFolderSummary({
      children: [folder("nested", [file("x.mp3", 999999)])],
      folder_count: 1,
      file_count: 0,
      file_size: 0,
    });

    expect(text).toBe("0 B\nfolders x1");
  });

  it("says Calculating… while the deep totals are on the way", () => {
    expect(
      formatFolderSummary(
        { children: [], folder_count: 0, file_count: 0 },
        {
          loading: true,
        },
      ),
    ).toBe("Calculating…");

    expect(
      formatFolderSummary(
        { children: null, folder_count: 2, file_count: 3, file_size: 1024 },
        { loading: true },
      ),
    ).toBe("Calculating…\n1 KB\nfolders x2");
  });

  it("prefers the deep format counts from the summary endpoint", () => {
    const text = formatFolderSummary({
      children: [{ name: "a.mp3", type: "file", size: 1024 }],
      folder_count: 3,
      file_count: 40,
      file_size: 3072,
      format_counts: { FLAC: 39, MP3: 1 },
    });

    expect(text).toBe("3 KB\nfolders x3\nflac x39\nmp3 x1");
  });

  it("collapses the format list past the cap", () => {
    /** @type {Record<string, number>} */
    const format_counts = {};
    for (let index = 0; index < 9; index += 1) {
      format_counts[`F${index}`] = 9 - index;
    }

    const lines = formatFolderSummary({
      folder_count: 0,
      file_count: 45,
      file_size: 0,
      format_counts,
    }).split("\n");

    // size + five formats + the collapsed remainder
    expect(lines).toHaveLength(1 + MAX_FORMAT_LINES + 1);
    expect(lines.at(-1)).toBe("+4 more formats");
  });
});

describe("formatFileSize", () => {
  it("formats bytes and kilobytes", () => {
    expect(formatFileSize(0)).toBe("0 B");
    expect(formatFileSize(1536)).toBe("1.5 KB");
  });
});
