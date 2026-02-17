// src/stores/context.store.js

import { writable } from 'svelte/store';

export const contextMenu = writable({
  isOpen: false,
  path: null,
  x: 0,
  y: 0,
  type: null
});

export const renamingPath = writable(null);