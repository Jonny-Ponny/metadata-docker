// @ts-check
import { describe, expect, it } from "vitest";
import { sortItems } from "../sort.utils.js";

/**
 * @param {string} name
 * @param {Record<string, any>} [extra]
 */
const directory = (name, extra = {}) => ({
  type: "directory",
  name,
  ...extra,
});

/**
 * @param {string} name
 * @param {Record<string, any>} [extra]
 */
const file = (name, extra = {}) => ({
  type: "file",
  name,
  ...extra,
});

describe("sortItems", () => {
  it("returns empty and missing input unchanged", () => {
    /** @type {any[]} */
    const items = [];
    expect(sortItems(items, "name", "asc")).toBe(items);
    expect(sortItems(/** @type {any} */ (null), "name", "asc")).toBeNull();
  });

  it("sorts directories before files", () => {
    const result = sortItems(
      [file("a.mp3"), directory("z"), file("b.mp3"), directory("a")],
      "name",
      "asc",
    );

    expect(result.map((item) => `${item.type}:${item.name}`)).toEqual([
      "directory:a",
      "directory:z",
      "file:a.mp3",
      "file:b.mp3",
    ]);
  });

  it("sorts names case-insensitively", () => {
    const result = sortItems(
      [file("beta.mp3"), file("Alpha.mp3"), file("gamma.mp3")],
      "name",
      "asc",
    );

    expect(result.map((item) => item.name)).toEqual([
      "Alpha.mp3",
      "beta.mp3",
      "gamma.mp3",
    ]);
  });

  it("sorts names descending", () => {
    const result = sortItems(
      [directory("a"), directory("c"), directory("b")],
      "name",
      "desc",
    );

    expect(result.map((item) => item.name)).toEqual(["c", "b", "a"]);
  });

  it("sorts by creation time and treats a missing value as 0", () => {
    const result = sortItems(
      [
        file("later.mp3", { created: 300 }),
        file("missing.mp3"),
        file("earlier.mp3", { created: 100 }),
      ],
      "created",
      "asc",
    );

    expect(result.map((item) => item.name)).toEqual([
      "missing.mp3",
      "earlier.mp3",
      "later.mp3",
    ]);
  });

  it("sorts by modification time descending", () => {
    const result = sortItems(
      [
        file("old.mp3", { modified: "100" }),
        file("new.mp3", { modified: 300 }),
        file("middle.mp3", { modified: 200 }),
      ],
      "modified",
      "desc",
    );

    expect(result.map((item) => item.name)).toEqual([
      "new.mp3",
      "middle.mp3",
      "old.mp3",
    ]);
  });

  it("falls back to name sorting for unknown modes", () => {
    const result = sortItems([file("b.mp3"), file("a.mp3")], "unknown", "asc");

    expect(result.map((item) => item.name)).toEqual(["a.mp3", "b.mp3"]);
  });
});
