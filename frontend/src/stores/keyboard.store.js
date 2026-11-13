// src/stores/keyboard.store.js

// Guards for global keyboard shortcuts.
//
// App.svelte listens on `window` for F2, Delete and the tree navigation keys.
// Those must do nothing while the user is typing, renaming a tree row or has a
// modal open. The checks live here (rather than inline in the listener) so the
// components can share them and the rules have their own tests.

import { get, writable } from "svelte/store";

import { contextMenu, renamingPath } from "./context.store.js";

const TYPING_SELECTOR = "input, textarea, select, [contenteditable='true']";

/**
 * Whether an event target or the focused element is a text input.
 * @param {EventTarget | Element | null | undefined} target
 * @returns {boolean}
 */
export function isTypingTarget(target) {
  if (
    !target ||
    typeof (/** @type {Element} */ (target).closest) !== "function"
  )
    return false;
  return !!(/** @type {Element} */ (target).closest(TYPING_SELECTOR));
}

/**
 * Whether a modal or the context menu currently owns the keyboard.
 *
 * Modals render `.modal-content` / `.help-modal`; rename inputs and the
 * context menu are separate states that do not always focus an input.
 * @returns {boolean}
 */
export function isOverlayOpen() {
  if (typeof document === "undefined") return false;
  if (get(renamingPath) !== null) return true;
  if (get(contextMenu).isOpen) return true;
  return !!document.querySelector(
    ".modal-content, .help-modal, .edit-modal, .image-viewer-overlay",
  );
}

/**
 * Whether a keyboard shortcut should be ignored for this event.
 * @param {KeyboardEvent} event
 * @returns {boolean}
 */
export function shouldIgnoreShortcut(event) {
  if (event.defaultPrevented) return true;
  const active = /** @type {Element | null} */ (document.activeElement);
  return (
    isTypingTarget(event.target) || isTypingTarget(active) || isOverlayOpen()
  );
}

/**
 * Whether the pointer is over the library tree. The modal guard above would
 * otherwise keep arrow keys from working after a modal closed without moving
 * focus back.
 * @param {EventTarget | Element | null | undefined} target
 * @returns {boolean}
 */
export function isInsideTree(target) {
  if (!target || !(target instanceof Element)) return false;
  return !!target.closest(".file-tree-panel");
}

/**
 * Whether a key is a plain character that type-ahead may consume. Modifier
 * combinations and keys handled by the browser stay untouched.
 * @param {KeyboardEvent} event
 * @returns {boolean}
 */
export function isTypeAheadKey(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  return event.key.length === 1 && event.key !== " ";
}

// State for the tree's roving focus: the row the tree cursor is on. It is kept
// apart from `selectedFile` / `selectedFolder` because moving the cursor must
// not load audio or fetch metadata; only Enter selects.
/** @type {import("svelte/store").Writable<string | null>} */
export const treeCursor = writable(/** @type {string | null} */ (null));

/**
 * Pointer-over state of the tree focus model. A plain click on a row is a
 * navigation, so the next letter typed is type-ahead; a double click is an
 * activation, so typing goes to whatever control was clicked instead.
 * @type {import("svelte/store").Writable<"navigation" | "activation">}
 */
export const treeFocusMode = writable(
  /** @type {"navigation" | "activation"} */ ("navigation"),
);
