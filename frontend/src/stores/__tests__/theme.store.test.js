import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

/**
 * @param {boolean} matches
 */
function stubPrefersDark(matches) {
  const matchMedia = vi.fn().mockReturnValue({ matches });
  vi.stubGlobal("matchMedia", matchMedia);
  return matchMedia;
}

describe("theme store", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("requestAnimationFrame", (/** @type {() => void} */ cb) => {
      cb();
      return 1;
    });
    document.body.className = "";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    document.body.className = "";
    document.querySelector('link[rel="icon"][type="image/svg+xml"]')?.remove();
  });

  it("defaults to light when the system prefers light", async () => {
    stubPrefersDark(false);

    const { theme } = await import("../theme.store.js");

    expect(get(theme)).toBe("light");
    expect(document.body.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("uses the system preference on first load", async () => {
    stubPrefersDark(true);

    const { theme } = await import("../theme.store.js");

    expect(get(theme)).toBe("dark");
    expect(document.body.classList.contains("dark")).toBe(true);
  });

  it("prefers the saved theme over the system preference", async () => {
    localStorage.setItem("theme", "light");
    stubPrefersDark(true);

    const { theme } = await import("../theme.store.js");

    expect(get(theme)).toBe("light");
    expect(document.body.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("toggles between light and dark", async () => {
    stubPrefersDark(false);
    const { theme, toggleTheme } = await import("../theme.store.js");

    toggleTheme();

    expect(get(theme)).toBe("dark");
    expect(document.body.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");

    toggleTheme();

    expect(get(theme)).toBe("light");
    expect(document.body.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("disables transitions only while the theme changes", async () => {
    stubPrefersDark(false);
    await import("../theme.store.js");

    expect(document.body.classList.contains("no-transitions")).toBe(true);

    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(document.body.classList.contains("no-transitions")).toBe(false);
  });
});
