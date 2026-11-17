// src/utils/contextMenu.utils.js

/**
 * Keep the context menu inside the viewport.
 *
 * The menu is `position: fixed`, so everything here is in viewport
 * coordinates. A menu opened on a row near the bottom used to be moved up by
 * its height and then clamped to the top edge, which put its bottom past the
 * window as soon as it grew taller than the space below the row. Flipping only
 * when the flipped position actually fits, and capping the height instead of
 * sliding the whole menu off-screen, keeps every item reachable.
 *
 * @typedef {Object} MenuSize
 * @property {number} width
 * @property {number} height
 *
 * @typedef {Object} MenuPlacement
 * @property {number} left
 * @property {number} top
 * @property {number | undefined} maxHeight set only when the menu has to be
 *   capped to fit, so the list scrolls instead of overflowing the window
 *
 * @param {{ x: number, y: number }} anchor the pointer position, or the centre
 *   of the row when the menu is opened from the keyboard
 * @param {MenuSize} size the menu's preferred size
 * @param {MenuSize} viewport the window's inner size
 * @param {number} [margin] gap kept between the menu and the window edge
 * @returns {MenuPlacement}
 */
export function placeMenu(anchor, size, viewport, margin = 8) {
  const fitsBelow = anchor.y + size.height <= viewport.height - margin;
  const fitsAbove = anchor.y - size.height >= margin;
  const fitsRight = anchor.x + size.width <= viewport.width - margin;

  // Prefer the pointer quadrant, as a native menu does; flip when the preferred
  // side has no room.
  let left = fitsRight ? anchor.x : anchor.x - size.width;
  let top = fitsBelow ? anchor.y : anchor.y - size.height;

  // A menu taller than the viewport fits on neither side. Anchoring it to one
  // edge and limiting its height is the only placement that keeps the last
  // item reachable.
  let maxHeight;
  if (!fitsBelow && !fitsAbove) {
    top = margin;
    maxHeight = viewport.height - margin * 2;
  }

  // Final clamp, so a menu wider than the viewport or a pointer at the very
  // edge cannot push it off-screen. `max(0, …)` matters when the window is
  // smaller than the margin.
  left = Math.max(margin, Math.min(left, viewport.width - size.width - margin));
  if (maxHeight === undefined) {
    top = Math.max(
      margin,
      Math.min(top, viewport.height - size.height - margin),
    );
  }
  top = Math.max(0, top);

  return { left: Math.max(0, left), top, maxHeight };
}
