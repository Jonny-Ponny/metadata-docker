// src/utils/image.utils.js

/**
 * Format an image's natural dimensions for display.
 *
 * Returns `null` until the browser has decoded a real image, so callers can
 * use it to guard the label instead of rendering `0x0px`.
 *
 * @param {number | null | undefined} width
 * @param {number | null | undefined} height
 * @returns {string | null}
 */
export function formatImageDimensions(width, height) {
  if (typeof width !== "number" || typeof height !== "number") return null;
  if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
  if (width <= 0 || height <= 0) return null;
  return `${width}x${height}px`;
}
