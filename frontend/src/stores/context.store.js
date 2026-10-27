// src/stores/context.store.js

import { writable } from "svelte/store";

/**
 * @typedef {Object} ContextMenuState
 * @property {boolean} isOpen
 * @property {string | null} path
 * @property {number} x
 * @property {number} y
 * @property {string | null} type
 */

export const contextMenu = writable(
  /** @type {ContextMenuState} */ ({
    isOpen: false,
    path: null,
    x: 0,
    y: 0,
    type: null,
  }),
);

export const renamingPath = writable(/** @type {string | null} */ (null));
