import { describe, expect, it } from "vitest";

import {
  buildBatchBody,
  collectAudioFiles,
  computeCommonValues,
  isValidDiskNumber,
} from "../bulkEdit.utils.js";

const tree = {
  name: "album",
  path: "album",
  type: "directory",
  children: [
    { name: "01.mp3", path: "album/01.mp3", type: "file", file_type: "audio" },
    { name: "cover.jpg", path: "album/cover.jpg", type: "file" },
    {
      name: "cd2",
      path: "album/cd2",
      type: "directory",
      children: [
        {
          name: "01.flac",
          path: "album/cd2/01.flac",
          type: "file",
          file_type: "audio",
        },
      ],
    },
  ],
};

describe("collectAudioFiles", () => {
  it("lists only direct audio children when not recursive", () => {
    expect(collectAudioFiles(tree, false)).toEqual([
      { path: "album/01.mp3", name: "01.mp3", relativePath: "01.mp3" },
    ]);
  });

  it("walks subfolders when recursive", () => {
    expect(collectAudioFiles(tree, true).map((f) => f.relativePath)).toEqual([
      "01.mp3",
      "cd2/01.flac",
    ]);
  });

  it("stops at the limit", () => {
    expect(collectAudioFiles(tree, true, 1)).toHaveLength(1);
  });

  it("returns nothing for missing or non-folder nodes", () => {
    expect(collectAudioFiles(null, true)).toEqual([]);
    expect(
      collectAudioFiles({ name: "a", path: "a", type: "file" }, true),
    ).toEqual([]);
  });
});

describe("computeCommonValues", () => {
  it("reports shared values and mixed fields", () => {
    const result = computeCommonValues(
      [
        { artist: "A", album: "X" },
        { artist: "A", album: "Y" },
      ],
      ["artist", "album", "genre"],
    );

    expect(result).toEqual({
      artist: { value: "A", mixed: false },
      album: { value: "", mixed: true },
      genre: { value: "", mixed: false },
    });
  });

  it("treats a missing value as different from a set one", () => {
    const result = computeCommonValues([{ genre: "Rock" }, {}], ["genre"]);
    expect(result.genre).toEqual({ value: "", mixed: true });
  });

  it("is not mixed for an empty list", () => {
    expect(computeCommonValues([], ["artist"]).artist).toEqual({
      value: "",
      mixed: false,
    });
  });
});

describe("isValidDiskNumber", () => {
  it.each(["1", "2/3", " 10/12 "])("accepts %s", (value) => {
    expect(isValidDiskNumber(value)).toBe(true);
  });

  it.each(["", "one", "1/", "/2", "1-2"])("rejects %s", (value) => {
    expect(isValidDiskNumber(value)).toBe(false);
  });
});

describe("buildBatchBody", () => {
  it("splits edits into set and delete", () => {
    expect(
      buildBatchBody(["a.mp3"], {
        artist: { action: "set", value: "A" },
        genre: { action: "delete" },
      }),
    ).toEqual({ paths: ["a.mp3"], set: { artist: "A" }, delete: ["genre"] });
  });
});
