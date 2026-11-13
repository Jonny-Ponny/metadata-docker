// src/utils/tree.utils.js

// Keyboard navigation over the lazy library tree.
//
// The tree is not a flat list in the DOM (folders render their children
// recursively and only the folders the user opened have been fetched), so
// navigating it by walking the DOM would be fragile. Instead the visible rows
// are derived from the same data the tree renders - the path-keyed cache from
// `stores/tree.store.js`, the expanded set and the current sort - and the
// cursor is an index into that list.
//
// Rows are library-relative paths; the library root is not a row.

import { sortItems } from "./sort.utils.js";

/**
 * One rendered row of the file tree.
 * @typedef {Object} VisibleRow
 * @property {string} path
 * @property {"file" | "directory" | string} type
 * @property {string} name
 * @property {number} level depth below the library root, 0 at the top
 * @property {boolean} expanded folder is open (and its children are visible)
 * @property {boolean} hasChildren folder may have children to expand
 * @property {string} parentPath folder above the row, `""` for the top level
 */

/**
 * The shape of a tree entry this module reads. Tree nodes carry more fields.
 * @typedef {Object} TreeEntry
 * @property {string} name
 * @property {string} path
 * @property {string} type
 * @property {TreeEntry[] | null} [children]
 * @property {boolean} [has_children]
 * @property {string | number} [created]
 * @property {string | number} [modified]
 */

/**
 * Parent folder of a library-relative path.
 * @param {string} path
 * @returns {string}
 */
function parentOf(path) {
  const index = path.lastIndexOf("/");
  return index === -1 ? "" : path.slice(0, index);
}

/**
 * Whether a folder can be expanded. A folder known to be empty (`has_children
 * false`) and a loaded folder with no entries cannot be.
 * @param {TreeEntry} entry
 * @param {TreeEntry[]} children
 * @returns {boolean}
 */
function folderHasChildren(entry, children) {
  if (entry.has_children === false) return false;
  return entry.has_children === true || children.length > 0;
}

/**
 * Children of a folder as the tree renders them: the lazy cache first, then a
 * nested `children` array (a fully loaded `/api/files` response), sorted with
 * the tree's current order.
 * @param {TreeEntry} entry
 * @param {Map<string, TreeEntry[]>} childrenByPath
 * @param {{ by: string, direction: string }} sortConfig
 * @returns {TreeEntry[]}
 */
function childrenOf(entry, childrenByPath, sortConfig) {
  if (entry.type !== "directory") return [];
  const cached = childrenByPath.get(entry.path) ?? entry.children ?? [];
  if (!cached.length) return [];
  return /** @type {TreeEntry[]} */ (
    /** @type {unknown} */ (
      sortItems(cached, sortConfig.by, sortConfig.direction)
    )
  );
}

/**
 * The rows the tree shows, top to bottom.
 *
 * Mirrors the rendering rules of `TreeNode.svelte`: children come from the
 * cache when it has the folder, sorted per folder, and a folder's subtree is
 * only listed while the caller's expanded set says it is open. Passing the set
 * from the App (which adds the search-only expansion) keeps keyboard order
 * identical to what is on screen.
 *
 * @param {TreeEntry[]} nodes top-level entries
 * @param {Map<string, TreeEntry[]>} childrenByPath
 * @param {{ has(path: string): boolean }} expanded
 * @param {{ by: string, direction: string }} sortConfig
 * @returns {VisibleRow[]}
 */
export function flattenVisibleRows(
  nodes,
  childrenByPath,
  expanded,
  sortConfig,
) {
  /** @type {VisibleRow[]} */
  const rows = [];

  /**
   * @param {TreeEntry[]} entries
   * @param {number} level
   */
  function walk(entries, level) {
    for (const entry of entries ?? []) {
      const isFolder = entry.type === "directory";
      const children = childrenOf(entry, childrenByPath, sortConfig);
      const isExpanded = isFolder && expanded.has(entry.path);

      rows.push({
        path: entry.path,
        type: entry.type,
        name: entry.name,
        level,
        expanded: isExpanded,
        hasChildren: isFolder && folderHasChildren(entry, children),
        parentPath: parentOf(entry.path),
      });

      if (isExpanded) walk(children, level + 1);
    }
  }

  walk(nodes, 0);
  return rows;
}

/**
 * Index of a path in the row list, or `-1`.
 * @param {VisibleRow[]} rows
 * @param {string | null | undefined} path
 * @returns {number}
 */
export function rowIndexOf(rows, path) {
  if (!path) return -1;
  return rows.findIndex((row) => row.path === path);
}

/**
 * Clamped "move by one row" target. Moving above the first row selects the
 * first row; moving below the last one selects the last row.
 * @param {VisibleRow[]} rows
 * @param {number} index current index, `-1` when nothing is focused
 * @param {number} delta
 * @returns {number}
 */
export function stepRow(rows, index, delta) {
  if (!rows.length) return -1;
  if (index < 0) return delta < 0 ? rows.length - 1 : 0;
  return Math.min(rows.length - 1, Math.max(0, index + delta));
}

/**
 * First row of the list, or `-1`.
 * @param {VisibleRow[]} rows
 * @returns {number}
 */
export function firstRow(rows) {
  return rows.length ? 0 : -1;
}

/**
 * Last row of the list, or `-1`.
 * @param {VisibleRow[]} rows
 * @returns {number}
 */
export function lastRow(rows) {
  return rows.length - 1;
}

/**
 * Index of the first child of an expanded folder, or `-1` when there is none.
 * The child follows the folder, so an expanded folder always has at least one
 * row after it; that row is either a child or the next sibling.
 * @param {VisibleRow[]} rows
 * @param {number} index
 * @returns {number}
 */
export function firstChildRow(rows, index) {
  const row = rows[index];
  if (!row || !row.expanded) return -1;
  const next = rows[index + 1];
  if (!next || next.level <= row.level) return -1;
  return index + 1;
}

/**
 * Index of the parent folder row, or `-1` at the top level.
 * @param {VisibleRow[]} rows
 * @param {number} index
 * @returns {number}
 */
export function parentRow(rows, index) {
  const row = rows[index];
  if (!row || !row.parentPath) return -1;
  return rowIndexOf(rows, row.parentPath);
}

/**
 * Index a page of rows away, keeping the cursor inside the list. `pageSize` is
 * the number of rows that fit in the panel.
 * @param {VisibleRow[]} rows
 * @param {number} index
 * @param {number} pageSize
 * @param {1 | -1} direction
 * @returns {number}
 */
export function pageRow(rows, index, pageSize, direction) {
  if (!rows.length) return -1;
  const size = Math.max(1, Math.floor(pageSize) || 1);
  return stepRow(rows, index, direction * size);
}

/**
 * Row matching a type-ahead prefix, starting after the cursor and wrapping
 * around once. Names are compared case-insensitively. Returns `-1` for an empty
 * prefix or no match.
 * @param {VisibleRow[]} rows
 * @param {string} prefix
 * @param {number} fromIndex
 * @returns {number}
 */
export function findByPrefix(rows, prefix, fromIndex) {
  const needle = String(prefix || "").toLowerCase();
  if (!needle || !rows.length) return -1;

  const below = rows.slice(fromIndex + 1);
  const above = rows.slice(0, Math.max(0, fromIndex + 1));
  for (const row of [...below, ...above]) {
    if (row.name.toLowerCase().startsWith(needle)) {
      return rows.indexOf(row);
    }
  }
  return -1;
}
