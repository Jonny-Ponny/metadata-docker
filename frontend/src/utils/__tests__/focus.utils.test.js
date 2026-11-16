import { afterEach, describe, expect, it, vi } from "vitest";

import {
  closeDialog,
  closeTopDialogOnEscape,
  dialogOpenEffect,
  focusableIn,
  isTopDialog,
  keepFocusInDialog,
  keepTabInDialog,
  openDialog,
  resetDialogStack,
} from "../focus.utils.js";

describe("focus utils", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    resetDialogStack();
  });

  /**
   * A dialog panel with three controls, appended to the body. The helpers read
   * the panel from `event.currentTarget`, so the tests dispatch through the
   * panel's own handler exactly as the components do.
   * @returns {{ panel: HTMLElement, first: HTMLButtonElement, middle: HTMLButtonElement, last: HTMLButtonElement }}
   */
  function dialog() {
    document.body.innerHTML = "";
    const panel = document.createElement("div");
    panel.innerHTML = [
      '<button id="first">first</button>',
      '<button id="middle">middle</button>',
      '<button id="last">last</button>',
    ].join("");
    document.body.appendChild(panel);
    return {
      panel,
      first: /** @type {HTMLButtonElement} */ (panel.querySelector("#first")),
      middle: /** @type {HTMLButtonElement} */ (panel.querySelector("#middle")),
      last: /** @type {HTMLButtonElement} */ (panel.querySelector("#last")),
    };
  }

  /**
   * Press Tab on `target`, handled by the dialog panel's own keydown listener.
   * @param {HTMLElement} panel
   * @param {HTMLElement} target
   * @param {boolean} [shiftKey]
   */
  function pressTab(panel, target, shiftKey = false) {
    const event = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey,
      bubbles: true,
      cancelable: true,
    });
    panel.addEventListener("keydown", keepTabInDialog, { once: true });
    target.dispatchEvent(event);
    return event;
  }

  /**
   * Send a focusin event to the panel, as focus landing outside it does.
   * @param {HTMLElement} panel
   */
  function focusEscaped(panel) {
    const event = new FocusEvent("focusin", { bubbles: true });
    panel.addEventListener("focusin", keepFocusInDialog, { once: true });
    panel.dispatchEvent(event);
    return event;
  }

  describe("focusableIn", () => {
    it("lists the tab stops in DOM order", () => {
      const { panel, first, middle, last } = dialog();

      expect(focusableIn(panel)).toEqual([first, middle, last]);
    });

    it("skips negative tab stops, hidden elements and display:none controls", () => {
      const { panel, last } = dialog();
      const icon = document.createElement("button");
      icon.tabIndex = -1;
      panel.appendChild(icon);
      const hiddenWrapper = document.createElement("div");
      hiddenWrapper.setAttribute("hidden", "");
      hiddenWrapper.innerHTML = "<button>hidden</button>";
      panel.appendChild(hiddenWrapper);
      const displayNone = document.createElement("button");
      displayNone.style.display = "none";
      panel.appendChild(displayNone);

      const stops = focusableIn(panel);
      expect(stops).toHaveLength(3);
      expect(stops).toContain(last);
      expect(stops).not.toContain(icon);
    });
  });

  describe("dialog stack", () => {
    it("only the topmost dialog closes on Escape", () => {
      // The lyrics editor opens its own text editor on top; both used to
      // listen on window, so one Escape closed both.
      const outer = document.createElement("div");
      const inner = document.createElement("div");
      document.body.append(outer, inner);
      openDialog(outer);
      openDialog(inner);
      const closeOuter = vi.fn();
      const closeInner = vi.fn();

      const event = new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      });

      expect(closeTopDialogOnEscape(event, outer, closeOuter)).toBe(false);
      expect(closeOuter).not.toHaveBeenCalled();
      expect(closeTopDialogOnEscape(event, inner, closeInner)).toBe(true);
      expect(closeInner).toHaveBeenCalledTimes(1);
    });

    it("the dialog underneath takes over once the top one closes", () => {
      const outer = document.createElement("div");
      const inner = document.createElement("div");
      openDialog(outer);
      openDialog(inner);
      closeDialog(inner);

      expect(isTopDialog(outer)).toBe(true);
      expect(isTopDialog(inner)).toBe(false);
    });
  });

  describe("dialogOpenEffect", () => {
    /**
     * Mount the effect for a dialog the way a component's `$effect` does.
     * @param {HTMLElement} panel
     * @param {() => void} onClose
     * @returns {() => void} the cleanup the component would run
     */
    function mountDialog(panel, onClose) {
      const cleanup = dialogOpenEffect(panel, true, onClose);
      expect(cleanup).toBeTypeOf("function");
      return /** @type {() => void} */ (cleanup);
    }

    it("returns focus to the control that opened the dialog", () => {
      const trigger = document.createElement("button");
      const panel = document.createElement("div");
      const field = document.createElement("textarea");
      panel.appendChild(field);
      document.body.append(trigger, panel);
      trigger.focus();

      const cleanup = mountDialog(panel, () => {});
      // Opening moves focus into the dialog, as every dialog here does.
      field.focus();
      expect(document.activeElement).toBe(field);

      cleanup();

      expect(document.activeElement).toBe(trigger);
      expect(isTopDialog(panel)).toBe(false);
    });

    it("returns focus to the opener even when the dialog moved focus inside", () => {
      const trigger = document.createElement("button");
      const panel = document.createElement("div");
      const field = document.createElement("textarea");
      panel.appendChild(field);
      document.body.append(trigger, panel);
      trigger.focus();

      const cleanup = mountDialog(panel, () => {});
      // A dialog usually focuses its first field after opening.
      field.focus();
      cleanup();

      expect(document.activeElement).toBe(trigger);
    });

    it("closes the dialog on Escape when it is on top", () => {
      const panel = document.createElement("div");
      const opener = document.createElement("button");
      document.body.append(opener, panel);
      opener.focus();
      const onClose = vi.fn();

      const cleanup = mountDialog(panel, onClose);
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", cancelable: true }),
      );

      expect(onClose).toHaveBeenCalledTimes(1);
      cleanup();
    });
  });

  describe("keepTabInDialog", () => {
    it("wraps Tab from the last control to the first", () => {
      const { panel, first, last } = dialog();
      last.focus();

      const event = pressTab(panel, last);

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(first);
    });

    it("leaves the move from the second-to-last control to the browser", () => {
      // The last control's next index equals the list length; clamping the
      // index instead of wrapping sent focus back to itself, so the helper must
      // not intervene here and must wrap only past the very end.
      const { panel, middle } = dialog();
      middle.focus();

      const event = pressTab(panel, middle);

      expect(event.defaultPrevented).toBe(false);
      expect(document.activeElement).toBe(middle);
    });

    it("leaves Tab in the middle of the dialog to the browser", () => {
      const { panel, first, middle } = dialog();
      first.focus();

      const event = pressTab(panel, first);

      expect(event.defaultPrevented).toBe(false);
      expect(document.activeElement).toBe(first);
      expect(document.activeElement).not.toBe(middle);
    });

    it("wraps Shift+Tab from the first control to the last", () => {
      const { panel, first, last } = dialog();
      first.focus();

      const event = pressTab(panel, first, true);

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(last);
    });

    it("pulls focus that escaped the dialog back to its first control", () => {
      const { panel, first } = dialog();
      const outside = document.createElement("button");
      document.body.appendChild(outside);
      outside.focus();

      // Tab handled by the dialog while focus is outside it.
      const event = pressTab(panel, panel);

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(first);
    });

    it("moves focus to the panel itself when it has no controls", () => {
      document.body.innerHTML = "";
      const panel = document.createElement("div");
      panel.tabIndex = -1;
      document.body.appendChild(panel);

      const event = pressTab(panel, panel);

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(panel);
    });

    it("ignores keys other than Tab", () => {
      const { panel, last } = dialog();
      last.focus();
      const event = new KeyboardEvent("keydown", {
        key: "ArrowDown",
        bubbles: true,
        cancelable: true,
      });

      panel.addEventListener("keydown", keepTabInDialog, { once: true });
      last.dispatchEvent(event);

      expect(event.defaultPrevented).toBe(false);
      expect(document.activeElement).toBe(last);
    });
  });

  describe("keepFocusInDialog", () => {
    it("moves focus to the first control when it landed on the body", () => {
      const { panel, first } = dialog();
      document.body.focus();

      const moved = focusEscaped(panel);

      expect(moved.defaultPrevented).toBe(false);
      expect(document.activeElement).toBe(first);
      expect(panel.contains(document.activeElement)).toBe(true);
    });

    it("leaves focus inside the dialog alone", () => {
      const { panel, middle } = dialog();
      middle.focus();

      focusEscaped(panel);

      expect(document.activeElement).toBe(middle);
    });

    it("pulls focus back from a control behind the dialog", () => {
      const { panel, first } = dialog();
      const behind = document.createElement("button");
      document.body.appendChild(behind);
      behind.focus();

      focusEscaped(panel);

      expect(document.activeElement).toBe(first);
    });
  });
});
