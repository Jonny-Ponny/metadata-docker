import { writable } from "svelte/store";

/**
 * @typedef {Object} HoldToConfirmOptions
 * @property {number} [duration]
 * @property {(event: Event) => void} [onConfirm]
 * @property {(event: Event) => void} [onStart]
 * @property {(event: Event) => void} [onCancel]
 * @property {(progress: number) => void} [onProgress]
 */

/**
 * @param {HTMLElement} node
 * @param {HoldToConfirmOptions} [options]
 */
export function createHoldToConfirm(node, options = {}) {
  const {
    duration = 800, // Hold duration in ms
    onConfirm = () => {},
    onStart = () => {},
    onCancel = () => {},
    onProgress = () => {},
  } = options;

  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let timeoutId;
  /** @type {number} */
  let startTime = 0;
  /** @type {ReturnType<typeof setInterval> | undefined} */
  let progressInterval;
  let isHolding = false;

  // Progress store for visual feedback
  const progress = writable(0);

  /**
   * @param {Event} e
   */
  function startHold(e) {
    e.preventDefault();
    if (isHolding) return;

    isHolding = true;
    startTime = Date.now();
    onStart(e);

    // Update progress periodically
    progressInterval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const currentProgress = Math.min(elapsed / duration, 1);
      progress.set(currentProgress);
      onProgress(currentProgress);

      if (currentProgress >= 1) {
        completeHold(e);
      }
    }, 16); // ~60fps

    // Set timeout for completion
    timeoutId = setTimeout(() => {
      completeHold(e);
    }, duration);
  }

  /**
   * @param {Event} e
   */
  function completeHold(e) {
    if (!isHolding) return;

    cleanup();
    progress.set(1);
    onConfirm(e);
  }

  /**
   * @param {Event} e
   */
  function cancelHold(e) {
    if (!isHolding) return;

    cleanup();
    progress.set(0);
    onCancel(e);
  }

  function cleanup() {
    isHolding = false;
    clearTimeout(timeoutId);
    clearInterval(progressInterval);
  }

  // Event listeners
  node.addEventListener("mousedown", startHold);
  node.addEventListener("mouseup", cancelHold);
  node.addEventListener("mouseleave", cancelHold);
  node.addEventListener("touchstart", startHold);
  node.addEventListener("touchend", cancelHold);
  node.addEventListener("touchcancel", cancelHold);

  return {
    destroy() {
      cleanup();
      node.removeEventListener("mousedown", startHold);
      node.removeEventListener("mouseup", cancelHold);
      node.removeEventListener("mouseleave", cancelHold);
      node.removeEventListener("touchstart", startHold);
      node.removeEventListener("touchend", cancelHold);
      node.removeEventListener("touchcancel", cancelHold);
    },

    // Expose progress store
    progress,
  };
}

// Svelte action version
/**
 * @param {HTMLElement} node
 * @param {HoldToConfirmOptions} [options]
 */
export function holdToConfirm(node, options) {
  const holdInstance = createHoldToConfirm(node, options);

  return {
    destroy: holdInstance.destroy,

    /**
     * @param {HoldToConfirmOptions} [newOptions]
     */
    update(newOptions) {
      holdInstance.destroy();
      Object.assign(holdInstance, createHoldToConfirm(node, newOptions));
    },
  };
}
