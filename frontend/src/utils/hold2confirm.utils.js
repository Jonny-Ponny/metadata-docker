import { writable } from "svelte/store";

/**
 * @typedef {Object} HoldToConfirmOptions
 * @property {number} [duration]
 * @property {(event: Event) => void} [onConfirm]
 * @property {(event: Event) => void} [onStart]
 * @property {(event: Event) => void} [onCancel]
 * @property {(progress: number) => void} [onProgress]
 * @property {() => boolean} [isPointerHolding] returns true while a pointer
 *   hold is running, so the keyboard can refuse to start a second one
 */

/** @type {HoldToConfirmOptions} */
const EMPTY = {};

/**
 * The timing half of hold-to-confirm: start a hold, report progress, confirm
 * after `duration`, cancel early. Pointer events and the keyboard share it, so
 * both gestures have exactly the same feel.
 *
 * @param {HoldToConfirmOptions} options
 */
export function createHold(options = EMPTY) {
  // Options are read from this reference at call time so `update()` can swap
  // them without losing a hold that is already running.
  let current = options;

  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let timeoutId;
  let startTime = 0;
  /** @type {ReturnType<typeof setInterval> | undefined} */
  let progressInterval;
  let isHolding = false;

  const progress = writable(0);

  /** @param {number} value */
  function report(value) {
    progress.set(value);
    current.onProgress?.(value);
  }

  /** @param {Event} e */
  function start(e) {
    if (isHolding) return;

    isHolding = true;
    startTime = Date.now();
    current.onStart?.(e);

    progressInterval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      report(Math.min(elapsed / (current.duration ?? 800), 1));
      if (elapsed >= (current.duration ?? 800)) complete(e);
    }, 16); // ~60fps

    timeoutId = setTimeout(() => complete(e), current.duration ?? 800);
  }

  /** @param {Event} e */
  function complete(e) {
    if (!isHolding) return;

    cleanup();
    report(1);
    current.onConfirm?.(e);
  }

  /** @param {Event} e */
  function cancel(e) {
    if (!isHolding) return;

    cleanup();
    report(0);
    current.onCancel?.(e);
  }

  function cleanup() {
    isHolding = false;
    clearTimeout(timeoutId);
    clearInterval(progressInterval);
  }

  return {
    start,
    cancel,
    cleanup,
    progress,
    /** Whether a hold is currently running (pointer or keyboard). */
    get isHolding() {
      return isHolding;
    },
    /** @param {HoldToConfirmOptions} next */
    update(next) {
      current = next;
    },
  };
}

/**
 * A pointer hold on an element. The returned object also exposes the keyboard
 * entry points, so a component can run both gestures on one timer.
 *
 * @param {HTMLElement} node
 * @param {HoldToConfirmOptions} [options]
 */
export function createHoldToConfirm(node, options = EMPTY) {
  const hold = createHold(options);

  /** @param {Event} e */
  function pointerStart(e) {
    e.preventDefault();
    hold.start(e);
  }

  /** @param {Event} e */
  function pointerEnd(e) {
    hold.cancel(e);
  }

  node.addEventListener("mousedown", pointerStart);
  node.addEventListener("mouseup", pointerEnd);
  node.addEventListener("mouseleave", pointerEnd);
  node.addEventListener("touchstart", pointerStart);
  node.addEventListener("touchend", pointerEnd);
  node.addEventListener("touchcancel", pointerEnd);

  function destroy() {
    hold.cleanup();
    node.removeEventListener("mousedown", pointerStart);
    node.removeEventListener("mouseup", pointerEnd);
    node.removeEventListener("mouseleave", pointerEnd);
    node.removeEventListener("touchstart", pointerStart);
    node.removeEventListener("touchend", pointerEnd);
    node.removeEventListener("touchcancel", pointerEnd);
  }

  return {
    node,
    hold,
    destroy,
    get isHolding() {
      return hold.isHolding;
    },
    progress: hold.progress,
  };
}

/**
 * Svelte action: hold the element to confirm.
 *
 * @param {HTMLElement} node
 * @param {HoldToConfirmOptions} [options]
 */
export function holdToConfirm(node, options) {
  /** @type {ReturnType<typeof createHoldToConfirm>} */
  let instance = createHoldToConfirm(node, options);

  return {
    destroy() {
      instance.destroy();
    },

    /**
     * Svelte calls this whenever the props move. Only the behaviour is
     * swapped; the listeners and the progress store stay put, so a hold that
     * is already running is not lost.
     * @param {HoldToConfirmOptions} [newOptions]
     */
    update(newOptions) {
      instance.hold.update(newOptions ?? EMPTY);
    },
  };
}
