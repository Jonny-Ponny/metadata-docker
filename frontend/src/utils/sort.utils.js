// src/utils/sort.utils.js

import { writable } from "svelte/store";

/**
 * Minimal shape the sorter reads; tree nodes carry many more fields.
 * @typedef {Object} SortableItem
 * @property {string} name
 * @property {string} [type]
 * @property {string | number} [created]
 * @property {string | number} [modified]
 */

export const sortConfig = writable({
  by: "name", // 'name', 'created', 'modified'
  direction: "asc", // 'asc' or 'desc'
});

// Helper function to sort items
/**
 * @template {SortableItem} T
 * @param {T[]} items
 * @param {string} sortBy
 * @param {string} direction
 * @returns {T[]}
 */
export function sortItems(items, sortBy, direction) {
  if (!items || items.length === 0) return items;

  // First, separate directories and files
  const directories = items.filter((item) => item.type === "directory");
  const files = items.filter((item) => item.type === "file");

  // Sort function
  /**
   * @param {SortableItem} a
   * @param {SortableItem} b
   * @returns {number}
   */
  const sorter = (a, b) => {
    let aVal, bVal;

    switch (sortBy) {
      case "created":
        aVal = a.created || 0;
        bVal = b.created || 0;
        break;
      case "modified":
        aVal = a.modified || 0;
        bVal = b.modified || 0;
        break;
      case "name":
      default:
        aVal = a.name.toLowerCase();
        bVal = b.name.toLowerCase();
        break;
    }

    // For timestamps, ensure we're comparing numbers
    if (sortBy === "created" || sortBy === "modified") {
      aVal = Number(aVal);
      bVal = Number(bVal);
    }

    // Compare based on direction
    if (direction === "asc") {
      return aVal > bVal ? 1 : -1;
    } else {
      return aVal < bVal ? 1 : -1;
    }
  };

  // Sort directories and files separately, then combine
  return [...directories.sort(sorter), ...files.sort(sorter)];
}
