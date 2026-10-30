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

/**
 * Read an image's natural size with a detached <img>, whose load listener is
 * attached before `src` is set. This does not depend on a displayed element's
 * load event, which some browsers can fire before it is wired up.
 *
 * @param {string} url
 * @returns {Promise<{ width: number, height: number } | null>}
 */
export function probeImageSize(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      resolve(
        image.naturalWidth > 0 && image.naturalHeight > 0
          ? { width: image.naturalWidth, height: image.naturalHeight }
          : null,
      );
    };
    image.onerror = () => resolve(null);
    image.src = url;
  });
}
