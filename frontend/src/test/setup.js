import { afterEach } from "vitest";

// jsdom keeps localStorage for the whole file, so a store test could leak
// session or settings data into the next one.
afterEach(() => {
  localStorage.clear();
});
