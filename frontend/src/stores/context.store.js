// src/stores/context.store.js

import { writable } from "svelte/store";

/**
 * @typedef {Object} ContextMenuState
 * @property {boolean} isOpen
 * @property {string | null} path
 * @property {number} x anchor: pointer position, or the row centre for the
 *   keyboard. See `placeMenu` in `utils/contextMenu.utils.js`.
 * @property {number} y
 * @property {string | null} type
 * @property {"pointer" | "keyboard"} mode how it was opened: the keyboard
 *   moves focus into the menu and gives it back on close, the pointer leaves
 *   focus where it was
 */

export const contextMenu = writable(
  /** @type {ContextMenuState} */ ({
    isOpen: false,
    path: null,
    x: 0,
    y: 0,
    type: null,
    mode: "pointer",
  }),
);

export const renamingPath = writable(/** @type {string | null} */ (null));
