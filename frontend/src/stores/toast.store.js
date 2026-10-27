// src/store/toast.store.js

// ========== TOAST STORE ==========

/**
 * @typedef {"info" | "success" | "error" | "warning"} ToastType
 * @typedef {Object} ToastItem
 * @property {string} id
 * @property {string} message
 * @property {ToastType} type
 * @property {number} duration
 */

export function createToastStore() {
  /** @type {((toasts: ToastItem[]) => void)[]} */
  let subscribers = [];
  /** @type {ToastItem[]} */
  let toasts = [];

  /**
   * @param {(toasts: ToastItem[]) => void} fn
   * @returns {() => void}
   */
  function subscribe(fn) {
    subscribers.push(fn);
    fn(toasts);

    return () => {
      subscribers = subscribers.filter((sub) => sub !== fn);
    };
  }

  function notify() {
    subscribers.forEach((fn) => fn(toasts));
  }

  function generateId() {
    return Date.now() + Math.random().toString(36).substr(2, 9);
  }

  /**
   * @param {string} message
   * @param {ToastType} [type]
   * @param {number} [duration]
   * @returns {string}
   */
  function show(message, type = "info", duration = 5000) {
    const id = generateId();
    toasts = [...toasts, { id, message, type, duration }];
    notify();

    // Auto-remove after duration
    setTimeout(() => {
      remove(id);
    }, duration);

    return id;
  }

  /**
   * @param {string} id
   */
  function remove(id) {
    toasts = toasts.filter((t) => t.id !== id);
    notify();
  }

  function clear() {
    toasts = [];
    notify();
  }

  /**
   * @param {string} message
   * @param {number} [duration]
   * @returns {string}
   */
  function success(message, duration = 5000) {
    return show(message, "success", duration);
  }

  /**
   * @param {string} message
   * @param {number} [duration]
   * @returns {string}
   */
  function error(message, duration = 5000) {
    return show(message, "error", duration);
  }

  /**
   * @param {string} message
   * @param {number} [duration]
   * @returns {string}
   */
  function warning(message, duration = 5000) {
    return show(message, "warning", duration);
  }

  /**
   * @param {string} message
   * @param {number} [duration]
   * @returns {string}
   */
  function info(message, duration = 5000) {
    return show(message, "info", duration);
  }

  return {
    subscribe,
    show,
    remove,
    clear,
    success,
    error,
    warning,
    info,
  };
}

// Create a singleton instance
export const toast = createToastStore();
