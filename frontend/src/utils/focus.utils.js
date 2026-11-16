// src/utils/focus.utils.js
//
// Dialogs: keeping the keyboard inside one, and deciding which one owns Escape.
//
// Every dialog in the app renders as an overlay plus a panel. Two things need
// app-wide coordination rather than per-component handling:
//
//  - Focus. The overlay covers the page for the pointer, but nothing stops Tab
//    from walking into the controls behind it.
//  - Escape. Dialogs are mounted while closed (and nested: the lyrics editor
//    opens its own edit dialog), so a plain window listener in every dialog
//    closes all of them at once. Only the topmost open dialog may react.
//
// Both are handled here so every dialog behaves identically.

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
 * Open dialogs, bottom to top. A dialog registers when it opens and unregisters
 * when it closes; the last entry is the one the user is looking at.
 * @type {HTMLElement[]}
 */
const dialogStack = [];

/**
 * Register a dialog as the topmost open one.
 * @param {HTMLElement | null | undefined} panel
 */
export function openDialog(panel) {
  if (!panel || dialogStack.includes(panel)) return;
  dialogStack.push(panel);
}

/**
 * Remove a dialog from the stack (it closed).
 * @param {HTMLElement | null | undefined} panel
 */
export function closeDialog(panel) {
  if (!panel) return;
  const index = dialogStack.indexOf(panel);
  if (index !== -1) dialogStack.splice(index, 1);
}

/**
 * Whether this panel is the topmost open dialog.
 * @param {HTMLElement | null | undefined} panel
 * @returns {boolean}
 */
export function isTopDialog(panel) {
  return !!panel && dialogStack[dialogStack.length - 1] === panel;
}

/**
 * The topmost open dialog panel, or `null` when none is open.
 * @returns {HTMLElement | null}
 */
export function topDialog() {
  return dialogStack[dialogStack.length - 1] ?? null;
}

/**
 * Clear the stack. Only for tests, so one case cannot leak a dialog into the
 * next.
 */
export function resetDialogStack() {
  dialogStack.length = 0;
}

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
 * Close the topmost dialog on Escape.
 *
 * Every dialog is mounted while closed and listens on `window`, so without this
 * a single Escape closes a dialog *and* the dialog that opened it (the lyrics
 * editor and its text edit dialog, for example). Only the panel at the top of
 * the stack reacts; it also stops the event so the dialogs underneath, and the
 * app's own Escape handling, do not see it.
 * @param {KeyboardEvent} event
 * @param {HTMLElement | null | undefined} panel the dialog asking to close
 * @param {() => void} onClose
 * @returns {boolean} whether this dialog handled the key
 */
export function closeTopDialogOnEscape(event, panel, onClose) {
  if (event.key !== "Escape") return false;
  if (!isTopDialog(panel)) return false;
  event.preventDefault();
  event.stopPropagation();
  onClose();
  return true;
}

/**
 * Register a dialog while it is open and close it on Escape when it is the
 * topmost one.
 *
 * Use as a one-liner in the dialog component:
 *
 * ```js
 * let panel = $state(null);
 * $effect(() => dialogOpenEffect(panel, isOpen, onClose));
 * ```
 *
 * The returned cleanup unregisters the dialog when it hides or unmounts, so a
 * closed dialog never claims Escape or the top of the stack.
 * @param {HTMLElement | null | undefined} panel
 * @param {boolean | undefined} open
 * @param {() => void} onClose
 * @returns {(() => void) | undefined}
 */
export function dialogOpenEffect(panel, open, onClose) {
  if (!open || !panel) return;
  const element = panel;
  openDialog(element);
  /**
   * @param {KeyboardEvent} event
   */
  const handleKeyDown = (event) => {
    closeTopDialogOnEscape(event, element, onClose);
  };
  window.addEventListener("keydown", handleKeyDown);
  return () => {
    window.removeEventListener("keydown", handleKeyDown);
    closeDialog(element);
  };
}

/**
 * The dialog panel an event was handled on.
 *
 * The helpers are wired to the panel's own handlers, so `currentTarget` is the
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
