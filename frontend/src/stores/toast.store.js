// src/store/toast.store.js

// ========== TOAST STORE ==========

export function createToastStore() {
  let subscribers = [];
  let toasts = [];

  function subscribe(fn) {
    subscribers.push(fn);
    fn(toasts);
    
    return () => {
      subscribers = subscribers.filter(sub => sub !== fn);
    };
  }

  function notify() {
    subscribers.forEach(fn => fn(toasts));
  }

  function generateId() {
    return Date.now() + Math.random().toString(36).substr(2, 9);
  }

  function show(message, type = 'info', duration = 5000) {
    const id = generateId();
    toasts = [...toasts, { id, message, type, duration }];
    notify();

    // Auto-remove after duration
    setTimeout(() => {
      remove(id);
    }, duration);

    return id;
  }

  function remove(id) {
    toasts = toasts.filter(t => t.id !== id);
    notify();
  }

  function clear() {
    toasts = [];
    notify();
  }

  function success(message, duration = 5000) {
    return show(message, 'success', duration);
  }

  function error(message, duration = 5000) {
    return show(message, 'error', duration);
  }

  function warning(message, duration = 5000) {
    return show(message, 'warning', duration);
  }

  function info(message, duration = 5000) {
    return show(message, 'info', duration);
  }

  return {
    subscribe,
    show,
    remove,
    clear,
    success,
    error,
    warning,
    info
  };
}

// Create a singleton instance
export const toast = createToastStore();