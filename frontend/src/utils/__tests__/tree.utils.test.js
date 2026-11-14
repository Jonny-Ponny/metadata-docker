import { describe, expect, it } from "vitest";

import {
  findByPrefix,
  firstChildRow,
  firstRow,
  flattenVisibleRows,
  lastRow,
  pageRow,
  parentRow,
  rowIndexOf,
  stepRow,
  treeRowId,
} from "../tree.utils.js";

/**
 * A folder entry as `/api/files/dir` returns it: no children until fetched.
 * @param {string} name
 * @param {Record<string, any>} [extra]
 */
const folder = (name, extra = {}) => ({
  type: "directory",
  name,
  path: name,
  ...extra,
});

/**
 * @param {string} name
 * @param {Record<string, any>} [extra]
 */
const file = (name, extra = {}) => ({
  type: "file",
  path: name,
  name,
  ...extra,
});

/** @type {{ by: string, direction: string }} */
const byName = { by: "name", direction: "asc" };

/**
 * Expanded set from a list of paths.
 * @param {string[]} paths
 */
function expandedSet(paths) {
  return { has: (/** @type {string} */ path) => paths.includes(path) };
}

/**
 * @param {import("../tree.utils.js").VisibleRow[]} rows
 */
const paths = (rows) => rows.map((row) => row.path);

describe("flattenVisibleRows", () => {
  /** @type {Map<string, any[]>} */
  const cache = new Map([
    ["", [folder("Albums", { has_children: true }), file("loose.flac")]],
    [
      "Albums",
      [
        folder("Albums/Disc 1", { name: "Disc 1", has_children: true }),
        file("Albums/cover.jpg"),
      ],
    ],
    [
      "Albums/Disc 1",
      [
        {
          type: "file",
          name: "song.mp3",
          path: "Albums/Disc 1/song.mp3",
        },
      ],
    ],
  ]);

  it("lists only the root while nothing is expanded", () => {
    expect(
      paths(flattenVisibleRows(cache.get(""), cache, expandedSet([]), byName)),
    ).toEqual(["Albums", "loose.flac"]);
  });

  it("walks into expanded folders with their depth", () => {
    const rows = flattenVisibleRows(
      cache.get(""),
      cache,
      expandedSet(["Albums", "Albums/Disc 1"]),
      byName,
    );

    expect(paths(rows)).toEqual([
      "Albums",
      "Albums/Disc 1",
      "Albums/Disc 1/song.mp3",
      "Albums/cover.jpg",
      "loose.flac",
    ]);
    expect(rows.map((row) => row.level)).toEqual([0, 1, 2, 1, 0]);
    expect(rows.map((row) => row.expanded)).toEqual([
      true,
      true,
      false,
      false,
      false,
    ]);
  });

  it("keeps the cursor order identical to the sort setting", () => {
    const desc = { by: "name", direction: "desc" };
    const rows = flattenVisibleRows(
      cache.get(""),
      cache,
      expandedSet(["Albums"]),
      desc,
    );

    // Folders stay before files, both in reverse name order.
    expect(paths(rows)).toEqual([
      "Albums",
      "Albums/Disc 1",
      "Albums/cover.jpg",
      "loose.flac",
    ]);
  });

  it("uses a nested children array when the cache has not loaded the folder", () => {
    const nested = [
      {
        ...folder("Nested"),
        has_children: true,
        children: [file("Nested/a.mp3"), file("Nested/b.mp3")],
      },
    ];
    /** @type {Map<string, any[]>} */
    const empty = new Map([["", nested]]);

    const rows = flattenVisibleRows(
      nested,
      empty,
      expandedSet(["Nested"]),
      byName,
    );
    expect(paths(rows)).toEqual(["Nested", "Nested/a.mp3", "Nested/b.mp3"]);
  });

  it("marks folders whose children are not loaded yet as expandable", () => {
    const rows = flattenVisibleRows(
      cache.get(""),
      cache,
      expandedSet([]),
      byName,
    );

    expect(rows[0]).toMatchObject({ path: "Albums", hasChildren: true });
    expect(rows[1]).toMatchObject({ path: "loose.flac", hasChildren: false });
  });

  it("treats an empty folder as not expandable", () => {
    const empty = [folder("Empty", { has_children: false })];
    const rows = flattenVisibleRows(
      empty,
      new Map([["", empty]]),
      expandedSet([]),
      byName,
    );

    expect(rows).toHaveLength(1);
    expect(rows[0].hasChildren).toBe(false);
  });

  it("handles a missing root and empty cache", () => {
    expect(flattenVisibleRows([], new Map(), expandedSet([]), byName)).toEqual(
      [],
    );
    expect(
      flattenVisibleRows(
        /** @type {any} */ (null),
        new Map(),
        expandedSet([]),
        byName,
      ),
    ).toEqual([]);
  });

  it("keeps an expanded folder that has no cache entry as a single row", () => {
    // Reaching an expanded folder without its children is what a load in
    // flight looks like; the row must stay and the list must not break.
    const nested = [folder("Lazy", { has_children: true })];
    const rows = flattenVisibleRows(
      nested,
      new Map([["", nested]]),
      expandedSet(["Lazy"]),
      byName,
    );

    expect(paths(rows)).toEqual(["Lazy"]);
    expect(rows[0].expanded).toBe(true);
  });
});

describe("row helpers", () => {
  /** @type {import("../tree.utils.js").VisibleRow[]} */
  const rows = [
    {
      path: "A",
      type: "directory",
      name: "A",
      level: 0,
      expanded: true,
      hasChildren: true,
      parentPath: "",
    },
    {
      path: "A/a.mp3",
      type: "file",
      name: "a.mp3",
      level: 1,
      expanded: false,
      hasChildren: false,
      parentPath: "A",
    },
    {
      path: "A/B",
      type: "directory",
      name: "B",
      level: 1,
      expanded: false,
      hasChildren: true,
      parentPath: "A",
    },
    {
      path: "C",
      type: "directory",
      name: "C",
      level: 0,
      expanded: true,
      hasChildren: false,
      parentPath: "",
    },
  ];

  it("finds rows by path", () => {
    expect(rowIndexOf(rows, "A/B")).toBe(2);
    expect(rowIndexOf(rows, "missing")).toBe(-1);
    expect(rowIndexOf(rows, null)).toBe(-1);
  });

  it("clamps stepping at both ends", () => {
    expect(stepRow(rows, 0, 1)).toBe(1);
    expect(stepRow(rows, 3, 1)).toBe(3);
    expect(stepRow(rows, 0, -1)).toBe(0);
    expect(stepRow(rows, 2, -1)).toBe(1);
  });

  it("starts from the ends when nothing is focused", () => {
    expect(stepRow(rows, -1, 1)).toBe(0);
    expect(stepRow(rows, -1, -1)).toBe(3);
  });

  it("returns -1 for an empty list", () => {
    expect(stepRow([], 0, 1)).toBe(-1);
    expect(firstRow([])).toBe(-1);
    expect(lastRow([])).toBe(-1);
    expect(pageRow([], 0, 5, 1)).toBe(-1);
  });

  it("finds the first and last rows", () => {
    expect(firstRow(rows)).toBe(0);
    expect(lastRow(rows)).toBe(3);
  });

  it("only descends into expanded folders", () => {
    expect(firstChildRow(rows, 0)).toBe(1);
    expect(firstChildRow(rows, 2)).toBe(-1);
    // Last row: no child, no next sibling.
    expect(firstChildRow(rows, 3)).toBe(-1);
  });

  it("does not descend when the next row is a sibling or uncle", () => {
    /** @type {import("../tree.utils.js").VisibleRow[]} */
    const emptyExpanded = [
      {
        path: "A",
        type: "directory",
        name: "A",
        level: 0,
        expanded: true,
        hasChildren: false,
        parentPath: "",
      },
      {
        path: "C",
        type: "directory",
        name: "C",
        level: 0,
        expanded: false,
        hasChildren: false,
        parentPath: "",
      },
    ];
    expect(firstChildRow(emptyExpanded, 0)).toBe(-1);
  });

  it("finds the parent folder", () => {
    expect(parentRow(rows, 1)).toBe(0);
    expect(parentRow(rows, 2)).toBe(0);
    expect(parentRow(rows, 0)).toBe(-1);
  });

  it("pages within the list without overshooting", () => {
    expect(pageRow(rows, 0, 2, 1)).toBe(2);
    expect(pageRow(rows, 3, 10, 1)).toBe(3);
    expect(pageRow(rows, 1, 10, -1)).toBe(0);
    expect(pageRow(rows, 0, 0, 1)).toBe(1);
  });

  it("finds the next name matching a prefix and wraps", () => {
    expect(findByPrefix(rows, "c", -1)).toBe(3);
    expect(findByPrefix(rows, "a", 0)).toBe(1);
    expect(findByPrefix(rows, "a", 1)).toBe(0);
    expect(findByPrefix(rows, "c", 3)).toBe(3);
    expect(findByPrefix(rows, "zzz", -1)).toBe(-1);
    expect(findByPrefix(rows, "", 0)).toBe(-1);
  });

  describe("treeRowId", () => {
    it("keeps ids apart for names that differ only outside [A-Za-z0-9]", () => {
      // The keyboard moves focus by id, so a collision freezes the cursor.
      const names = [
        "Zero Boys",
        "きくお",
        "そこに鳴る",
        "ゆよゆっぺ",
        "オカメP",
        "ピノキオピー",
        "ミドリ",
      ];
      const ids = names.map((name) => treeRowId(name));
      expect(new Set(ids).size).toBe(names.length);
    });

    it("stays readable for ASCII paths and honours the prefix", () => {
      expect(treeRowId("Zulu.flac")).toBe("tree-row-Zulu-2eflac");
      expect(treeRowId("Zulu.flac", "search-")).toBe(
        "search-tree-row-Zulu-2eflac",
      );
    });

    it("does not clash when letter codes could be ambiguous", () => {
      // "-2e" plus "flac" must not be reachable from a different name.
      expect(treeRowId("a.2e")).not.toBe(treeRowId("a-2e"));
    });
  });
});
