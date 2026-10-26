// @ts-check
// src/utils/favicon.utils.js
import iconSvg from "../assets/icon.svg?raw";

const DEFAULT_ACCENT = "#fd7d05";

/**
 * Rebuild the favicon from icon.svg, substituting the current accent color.
 * A favicon is rendered outside the document, so it cannot read CSS variables
 * (var(--color-primary)); we resolve the accent applied to :root and inline it.
 * In dark mode the lighter --color-primary-dark variant is used.
 */
export function updateFavicon() {
  if (typeof document === "undefined") return;

  const isDark = document.body?.classList.contains("dark");
  const accent =
    getComputedStyle(document.documentElement)
      .getPropertyValue(isDark ? "--color-primary-dark" : "--color-primary")
      .trim() || DEFAULT_ACCENT;

  // The SVG ships with the default accent; swap it for the live one.
  const svg = iconSvg.replace(DEFAULT_ACCENT, accent);
  const href = "data:image/svg+xml," + encodeURIComponent(svg);

  /** @type {HTMLLinkElement | null} */
  let link = document.querySelector('link[rel="icon"][type="image/svg+xml"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    link.type = "image/svg+xml";
    document.head.appendChild(link);
  }
  link.href = href;
}
