// src/utils/focus.utils.js
//
// Keeping the keyboard inside an open dialog (T-19).
//
// Every dialog in the app renders as an overlay plus a panel. The overlay covers
// the page for the pointer, but nothing stops Tab from walking into the controls
// behind it: a keyboard user can press Tab out of an open dialog and drive the
// page underneath. These helpers close that gap.
//
// They are driven from the panel's own `onkeydown` / `onfocusin` handlers rather
// than from a window listener, so a dialog only reacts to events that happened
// inside it and two dialogs never fight over the same key.

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button",
  "input",
  "select",
  "textarea",
  "[tabindex]",
  "[contenteditable='true']",
].join(",");

/**
 * Focusable descendants of a container, in DOM order.
 *
 * Negative tab stops are skipped on purpose: the tree icons and the editor's
 * per-field buttons are pointer-only and must not join the Tab cycle. Hidden
 * elements (the `hidden` attribute or `display: none`) are skipped too, so an
 * inactive tab or a collapsed section cannot take focus.
 * @param {HTMLElement} container
 * @returns {HTMLElement[]}
 */
export function focusableIn(container) {
  return /** @type {HTMLElement[]} */ (
    /** @type {unknown} */ (
      [...container.querySelectorAll(FOCUSABLE_SELECTOR)].filter((element) => {
        const tabIndex = /** @type {HTMLElement} */ (element).tabIndex;
        if (tabIndex < 0) return false;
        if (element.closest("[hidden]")) return false;
        return getComputedStyle(element).display !== "none";
      })
    )
  );
}

/**
 * Keep Tab inside one dialog: Tab on the last control wraps to the first and
 * Shift+Tab on the first wraps to the last. Focus that has already escaped the
 * dialog is pulled back to its first control instead of wrapping to the end,
 * so the user always lands somewhere visible.
 *
 * Call from the dialog panel's `onkeydown`; it does nothing for keys other than
 * Tab, so text fields keep their normal key handling.
 * @param {KeyboardEvent} event
 * @returns {boolean} whether focus was moved
 */
export function keepTabInDialog(event) {
  if (event.key !== "Tab") return false;
  const panel = dialogFrom(event);
  if (!panel) return false;
  const items = focusableIn(panel);
  if (!items.length) {
    event.preventDefault();
    panel.focus();
    return true;
  }
  const index = items.indexOf(
    /** @type {HTMLElement} */ (document.activeElement),
  );
  // Focus outside the dialog (removed, or behind it) is pulled to the first
  // control; otherwise Tab moves by one and wraps at either end.
  if (index !== -1) {
    const next = event.shiftKey ? index - 1 : index + 1;
    if (next >= 0 && next < items.length) return false;
  }
  event.preventDefault();
  const target =
    index !== -1 && event.shiftKey ? items[items.length - 1] : items[0];
  target.focus();
  return true;
}

/**
 * Pull focus back into the dialog when it has escaped to `body` or to a control
 * behind the overlay.
 *
 * An overlay click closes every dialog, so there is no pointer path that leaves
 * focus outside one; this covers the rest: a control that was removed while
 * focused, or a programmatic focus behind the dialog.
 * @param {FocusEvent} event a `focusin` event
 * @returns {boolean} whether focus was moved
 */
export function keepFocusInDialog(event) {
  const panel = dialogFrom(event);
  if (!panel) return false;
  const active = /** @type {Element | null} */ (document.activeElement);
  if (active && active !== document.body && panel.contains(active)) {
    return false;
  }
  (focusableIn(panel)[0] ?? panel).focus();
  return true;
}

/**
 * The dialog panel an event was handled on.
 *
 * Both helpers are wired to the panel's own handlers, so `currentTarget` is the
 * panel itself: no selector to keep in sync, and no ambiguity when two dialogs
 * share a class name or are mounted at the same time.
 * @param {KeyboardEvent | FocusEvent} event
 * @returns {HTMLElement | null}
 */
function dialogFrom(event) {
  const current = /** @type {Element | null} */ (event.currentTarget);
  if (!current) return null;
  return /** @type {HTMLElement} */ (current);
}
