import { afterEach, describe, expect, it, vi } from "vitest";

import { updateFavicon } from "../favicon.utils.js";

/**
 * @param {string} accent
 */
function stubAccent(accent) {
  vi.stubGlobal("getComputedStyle", () => ({
    getPropertyValue: () => accent,
  }));
}

/**
 * @returns {HTMLLinkElement | null}
 */
function iconLink() {
  return /** @type {HTMLLinkElement | null} */ (
    document.querySelector('link[rel="icon"][type="image/svg+xml"]')
  );
}

describe("updateFavicon", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.className = "";
    iconLink()?.remove();
  });

  it("creates the icon link from the accent colour", () => {
    const getPropertyValue = vi.fn(() => "#3366ff");
    vi.stubGlobal("getComputedStyle", () => ({ getPropertyValue }));

    updateFavicon();

    const link = iconLink();
    expect(getPropertyValue).toHaveBeenCalledWith("--color-primary");
    expect(link).toBeTruthy();
    expect(link?.href).toContain("data:image/svg+xml,");
    expect(decodeURIComponent(link?.href ?? "")).toContain("#3366ff");
    expect(document.body.classList.contains("dark")).toBe(false);
  });

  it("reuses an existing icon link", () => {
    stubAccent("#112233");
    const link = document.createElement("link");
    link.rel = "icon";
    link.type = "image/svg+xml";
    document.head.appendChild(link);

    updateFavicon();

    expect(document.querySelectorAll('link[rel="icon"]')).toHaveLength(1);
    expect(link.href).toContain("data:image/svg+xml,");
  });

  it("uses the dark accent in dark mode", () => {
    const getPropertyValue = vi.fn(() => "#00ff00");
    vi.stubGlobal("getComputedStyle", () => ({ getPropertyValue }));
    document.body.classList.add("dark");

    updateFavicon();

    expect(getPropertyValue).toHaveBeenCalledWith("--color-primary-dark");
    expect(decodeURIComponent(iconLink()?.href ?? "")).toContain("#00ff00");
  });

  it("falls back to the default accent when the variable is empty", () => {
    stubAccent("");

    updateFavicon();

    expect(decodeURIComponent(iconLink()?.href ?? "")).toContain("#fd7d05");
  });
});
