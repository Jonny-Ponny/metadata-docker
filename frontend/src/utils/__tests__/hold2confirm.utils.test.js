import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import { createHoldToConfirm, holdToConfirm } from "../hold2confirm.utils.js";

/**
 * @param {number} [duration]
 */
function setup(duration = 800) {
  const node = document.createElement("button");
  const options = {
    duration,
    onStart: vi.fn(),
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    onProgress: vi.fn(),
  };
  const instance = createHoldToConfirm(node, options);
  return { node, options, instance };
}

/**
 * @param {HTMLElement} node
 * @param {string} type
 */
function fire(node, type) {
  node.dispatchEvent(new MouseEvent(type, { bubbles: true }));
}

describe("hold2confirm", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reports progress and confirms after the hold duration", () => {
    const { node, options, instance } = setup(800);

    fire(node, "mousedown");
    expect(options.onStart).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(400);
    expect(get(instance.progress)).toBeCloseTo(0.5, 1);
    expect(options.onProgress).toHaveBeenCalled();

    vi.advanceTimersByTime(400);

    expect(options.onConfirm).toHaveBeenCalledTimes(1);
    expect(options.onCancel).not.toHaveBeenCalled();
    expect(get(instance.progress)).toBe(1);
  });

  it("cancels when the pointer is released early", () => {
    const { node, options, instance } = setup();

    fire(node, "mousedown");
    vi.advanceTimersByTime(200);
    fire(node, "mouseup");

    expect(options.onCancel).toHaveBeenCalledTimes(1);
    expect(get(instance.progress)).toBe(0);

    vi.advanceTimersByTime(1000);
    expect(options.onConfirm).not.toHaveBeenCalled();
  });

  it("cancels when the pointer leaves the element", () => {
    const { node, options } = setup();

    fire(node, "mousedown");
    fire(node, "mouseleave");

    expect(options.onCancel).toHaveBeenCalledTimes(1);
    expect(options.onConfirm).not.toHaveBeenCalled();
  });

  it("ignores a second hold started while one is running", () => {
    const { node, options } = setup();

    fire(node, "mousedown");
    fire(node, "mousedown");
    vi.advanceTimersByTime(800);

    expect(options.onStart).toHaveBeenCalledTimes(1);
    expect(options.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("supports touch events", () => {
    const { node, options } = setup(100);

    node.dispatchEvent(new Event("touchstart", { cancelable: true }));
    vi.advanceTimersByTime(100);

    expect(options.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("stops listening after destroy", () => {
    const { node, options, instance } = setup(100);

    instance.destroy();
    fire(node, "mousedown");
    vi.advanceTimersByTime(200);

    expect(options.onStart).not.toHaveBeenCalled();
    expect(options.onConfirm).not.toHaveBeenCalled();
  });

  it("updates the action with new options", () => {
    const node = document.createElement("button");
    const first = { onConfirm: vi.fn(), duration: 100 };
    const second = { onConfirm: vi.fn(), duration: 100 };
    const action = holdToConfirm(node, first);

    action.update(second);
    fire(node, "mousedown");
    vi.advanceTimersByTime(100);

    expect(first.onConfirm).not.toHaveBeenCalled();
    expect(second.onConfirm).toHaveBeenCalledTimes(1);

    action.destroy();
  });
});
