import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { contextMenu, renamingPath } from "../context.store.js";
import {
  isInsideTree,
  isOverlayOpen,
  isTypeAheadKey,
  isTypingTarget,
  shouldIgnoreShortcut,
  treeCursor,
  treeFocusMode,
} from "../keyboard.store.js";

/**
 * @param {{ target?: EventTarget | null, key?: string, ctrlKey?: boolean, metaKey?: boolean, altKey?: boolean, defaultPrevented?: boolean }} [init]
 * @returns {KeyboardEvent}
 */
function keydown(init = {}) {
  const { target, ...rest } = init;
  const event = new KeyboardEvent("keydown", {
    key: "a",
    bubbles: true,
    cancelable: true,
    ...rest,
  });
  if (target) target.dispatchEvent(event);
  return event;
}

/**
 * A focused element that `document.activeElement` should report.
 * @param {string} html
 * @returns {HTMLElement}
 */
function activeElement(html) {
  const host = document.createElement("div");
  host.innerHTML = html;
  const element = /** @type {HTMLElement} */ (host.firstElementChild);
  document.body.appendChild(host);
  element.focus();
  return element;
}

describe("keyboard guards", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    renamingPath.set(null);
    contextMenu.set({ isOpen: false, path: null, x: 0, y: 0, type: null });
    treeCursor.set(null);
    treeFocusMode.set("navigation");
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("detects typing targets", () => {
    expect(isTypingTarget(null)).toBe(false);
    expect(isTypingTarget(/** @type {any} */ ({}))).toBe(false);

    const input = document.createElement("input");
    expect(isTypingTarget(input)).toBe(true);
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    expect(isTypingTarget(editable)).toBe(true);
    const select = document.createElement("select");
    expect(isTypingTarget(select)).toBe(true);
    const plain = document.createElement("div");
    expect(isTypingTarget(plain)).toBe(false);
  });

  it("detects a typing target that contains the event target", () => {
    const input = document.createElement("input");
    const span = document.createElement("span");
    input.appendChild(span);
    expect(isTypingTarget(span)).toBe(true);
  });

  it("treats a rename as an open overlay", () => {
    expect(isOverlayOpen()).toBe(false);
    renamingPath.set("a.mp3");
    expect(isOverlayOpen()).toBe(true);
  });

  it("treats the context menu as an open overlay", () => {
    contextMenu.update((state) => ({ ...state, isOpen: true }));
    expect(isOverlayOpen()).toBe(true);
  });

  it("treats a rendered modal as an open overlay", () => {
    document.body.innerHTML = '<div class="modal-content"></div>';
    expect(isOverlayOpen()).toBe(true);

    document.body.innerHTML = '<div class="help-modal"></div>';
    expect(isOverlayOpen()).toBe(true);
  });

  it("ignores shortcuts while typing", () => {
    const input = activeElement("<input />");
    const event = keydown({
      target: input,
      key: "ArrowDown",
    });
    expect(shouldIgnoreShortcut(event)).toBe(true);
  });

  it("ignores shortcuts while a modal is open", () => {
    document.body.innerHTML = '<div class="modal-content"></div>';
    expect(shouldIgnoreShortcut(keydown())).toBe(true);
  });

  it("ignores an event another handler already handled", () => {
    const event = keydown();
    event.preventDefault();
    expect(shouldIgnoreShortcut(event)).toBe(true);
  });

  it("allows shortcuts on the page and in the tree", () => {
    const list = document.createElement("ul");
    document.body.appendChild(list);
    list.focus();
    expect(shouldIgnoreShortcut(keydown({ target: document.body }))).toBe(
      false,
    );
  });

  it("recognises the library tree", () => {
    const panel = document.createElement("div");
    panel.className = "file-tree-panel";
    const row = document.createElement("div");
    panel.appendChild(row);
    document.body.appendChild(panel);
    expect(isInsideTree(row)).toBe(true);
    expect(isInsideTree(document.body)).toBe(false);
    expect(isInsideTree(null)).toBe(false);
  });

  it("reserves plain characters for type-ahead", () => {
    expect(isTypeAheadKey(keydown({ key: "a" }))).toBe(true);
    expect(isTypeAheadKey(keydown({ key: " " }))).toBe(false);
    expect(isTypeAheadKey(keydown({ key: "Enter" }))).toBe(false);
    expect(isTypeAheadKey(keydown({ key: "a", ctrlKey: true }))).toBe(false);
    expect(isTypeAheadKey(keydown({ key: "a", metaKey: true }))).toBe(false);
    expect(isTypeAheadKey(keydown({ key: "a", altKey: true }))).toBe(false);
  });
});
