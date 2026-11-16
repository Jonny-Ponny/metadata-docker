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
  // A <summary> is focusable and toggles its details, so it is a tab stop.
  "summary",
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
 * Only real tab stops are listed, so the caller's idea of "the last control"
 * matches what Tab does:
 *
 *  - a disabled control is never focusable, even though it still reports
 *    `tabIndex === 0`. Missing this made a dialog with a disabled Apply button
 *    let Tab escape: the helper thought a button further down was the last one;
 *  - negative tab stops are skipped on purpose: the tree icons and the editor's
 *    per-field buttons are pointer-only and must not join the Tab cycle;
 *  - hidden elements (`hidden`, or `display: none`) cannot take focus either,
 *    and content of a closed `<details>` is not rendered at all.
 * @param {HTMLElement} container
 * @returns {HTMLElement[]}
 */
export function focusableIn(container) {
  return /** @type {HTMLElement[]} */ (
    /** @type {unknown} */ (
      [...container.querySelectorAll(FOCUSABLE_SELECTOR)].filter((element) => {
        const control = /** @type {HTMLElement} */ (element);
        if (control.tabIndex < 0) return false;
        // `:disabled` covers button, input, select, textarea, optgroup and
        // option, plus a fieldset that disables its children.
        if (control.matches(":disabled")) return false;
        if (element.closest("[hidden]")) return false;
        if (isInClosedDetails(element)) return false;
        return getComputedStyle(element).display !== "none";
      })
    )
  );
}

/**
 * Whether an element is inside a collapsed `<details>`.
 *
 * Its content is not rendered, so none of it is tabbable; counting it made the
 * dialog's idea of the last control disagree with what Tab does, and focus
 * escaped the dialog. A `<summary>` is the collapsed element's own control and
 * stays focusable.
 * @param {Element} element
 * @returns {boolean}
 */
function isInClosedDetails(element) {
  for (let node = element.parentElement; node; node = node.parentElement) {
    if (node instanceof HTMLDetailsElement && !node.open) {
      const summary = node.querySelector(":scope > summary");
      // The summary is the collapsed element's own control; everything else
      // inside it is hidden.
      return !summary || !summary.contains(element);
    }
  }
  return false;
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
  return keepTabInDialogWith(event, panel);
}

/**
 * The Tab wrap itself, against an explicit panel. Used by the panel's own
 * `onkeydown` and by the window-level fallback that runs when focus is still
 * outside the dialog.
 * @param {KeyboardEvent} event
 * @param {HTMLElement} panel
 * @returns {boolean} whether focus was moved
 */
export function keepTabInDialogWith(event, panel) {
  if (event.key !== "Tab") return false;
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
 * Register a dialog while it is open, close it on Escape when it is the
 * topmost one, and give focus back to its opener when it closes.
 *
 * Use as a one-liner in the dialog component:
 *
 * ```js
 * let panel = $state(null);
 * $effect(() => dialogOpenEffect(panel, isOpen, onClose));
 * ```
 *
 * The returned cleanup unregisters the dialog when it hides or unmounts, so a
 * closed dialog never claims Escape or the top of the stack, and restores the
 * focus that was on the opener before the dialog opened.
 * @param {HTMLElement | null | undefined} panel
 * @param {boolean | undefined} open
 * @param {() => void} onClose
 * @returns {(() => void) | undefined}
 */
export function dialogOpenEffect(panel, open, onClose) {
  if (!open || !panel) return;
  const element = panel;
  // Where focus was when the dialog opened: closing returns it there, so a
  // keyboard user carries on from the control they used rather than from the
  // top of the page. A trigger that was removed meanwhile falls back to none.
  const opener =
    document.activeElement instanceof HTMLElement &&
    !panel.contains(document.activeElement)
      ? document.activeElement
      : null;
  openDialog(element);
  // Move focus into the dialog. Without this it stays on the opener behind the
  // overlay, and Tab then walks the page underneath instead of the dialog. The
  // panel is focused rather than its first control, so a dialog that focuses
  // its own field (the fetcher's query input, the lyrics editor) still wins.
  // Deferred, because focusing from inside the effect re-enters the renderer's
  // update cycle and can loop.
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  const focusTimer = setTimeout(() => {
    if (!element.contains(document.activeElement)) element.focus();
  }, 0);
  /**
   * @param {KeyboardEvent} event
   */
  const handleKeyDown = (event) => {
    // Tab and Escape are handled at window level so they work even while focus
    // is still outside the dialog (for example on the opener): the panel's own
    // `onkeydown` only fires for events that start inside it.
    if (event.key === "Tab" && !event.defaultPrevented) {
      const top = topDialog();
      if (top && !top.contains(document.activeElement)) {
        keepTabInDialogWith(event, top);
        return;
      }
    }
    closeTopDialogOnEscape(event, element, onClose);
  };
  window.addEventListener("keydown", handleKeyDown);
  return () => {
    clearTimeout(focusTimer);
    window.removeEventListener("keydown", handleKeyDown);
    closeDialog(element);
    restoreFocus(opener);
  };
}

/**
 * Give focus back to the element that opened a dialog.
 *
 * A dialog can close because its trigger went away (the file was deleted, the
 * row was renamed); focus() on a detached element is a no-op, so the caller's
 * own focus handling stays in charge in that case.
 * @param {HTMLElement | null} opener
 * @returns {boolean} whether an opener was given focus
 */
function restoreFocus(opener) {
  if (!opener) return false;
  opener.focus();
  return true;
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

/**
 * Open a `<select>`'s dropdown from the keyboard.
 *
 * Browsers do not open a native select popup on Enter when the select sits in
 * a `position: fixed` overlay, so every dropdown inside a dialog looked
 * keyboard-inaccessible. `showPicker()` asks for the picker directly instead
 * of relying on the default action, which works there. Browsers without it
 * keep their own behaviour, so this is a fallback, never a replacement.
 *
 * Wire it as `onkeydown={(e) => openSelectOnEnter(e)}`.
 * @param {KeyboardEvent} event
 * @returns {boolean} whether the picker was requested
 */
export function openSelectOnEnter(event) {
  if (event.key !== "Enter") return false;
  const select = /** @type {Element | null} */ (event.currentTarget);
  if (
    !select ||
    typeof (/** @type {any} */ (select).showPicker) !== "function"
  ) {
    return false;
  }
  event.preventDefault();
  try {
    /** @type {any} */ (select).showPicker();
    return true;
  } catch {
    // `showPicker` throws when the select is disabled or hidden; the browser's
    // own handling is then the better fallback.
    return false;
  }
}
