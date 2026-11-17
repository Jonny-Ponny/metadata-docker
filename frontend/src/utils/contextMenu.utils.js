// src/utils/contextMenu.utils.js

/**
 * Keep a floating menu inside the free part of the viewport.
 *
 * The menu is `position: fixed`, so everything here is in viewport
 * coordinates. The free area is the window minus anything pinned to an edge —
 * `top` for chrome above the content and `bottom` for the player bar, which
 * shares the menu's stacking level and would otherwise paint over it.
 *
 * A menu opened on a row near the bottom used to be moved up by its height and
 * then clamped to the top edge, which put its bottom past the window as soon as
 * it grew taller than the space below the row. Here the menu prefers to open on
 * the side the pointer suggests, flips only when that side has no room, and —
 * when it fits on neither side — is pinned to the top of the free area with its
 * height capped, so the list scrolls instead of running off-screen.
 *
 * @typedef {Object} MenuSize
 * @property {number} width
 * @property {number} height
 *
 * @typedef {Object} Viewport
 * @property {number} width
 * @property {number} height
 * @property {number} [top] reserved strip at the top, in pixels
 * @property {number} [bottom] reserved strip at the bottom (the player bar),
 *   in pixels: the menu must not be placed over it
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
 * @param {Viewport} viewport the window's inner size and any reserved edges
 * @param {number} [margin] gap kept between the menu and the edge
 * @returns {MenuPlacement}
 */
export function placeMenu(anchor, size, viewport, margin = 8) {
  // The box the menu may occupy, in viewport coordinates.
  const top = (viewport.top ?? 0) + margin;
  const bottom = viewport.height - (viewport.bottom ?? 0) - margin;
  const available = Math.max(0, bottom - top);

  const fitsBelow = anchor.y + size.height <= bottom;
  const fitsAbove = anchor.y - size.height >= top;
  const fitsRight = anchor.x + size.width <= viewport.width - margin;

  // Prefer the pointer quadrant, as a native menu does.
  const left = fitsRight ? anchor.x : anchor.x - size.width;

  let placedTop;
  let maxHeight;
  if (fitsBelow) {
    // The normal case: the menu hangs from the pointer downwards.
    placedTop = anchor.y;
  } else if (anchor.y > bottom) {
    // The anchor is behind the player bar. A flip would still leave the menu
    // overlapping it, so slide the menu into the free area instead (and cap it
    // if it does not fit there either).
    if (available >= size.height) {
      placedTop = bottom - size.height;
    } else {
      placedTop = top;
      maxHeight = available;
    }
  } else if (fitsAbove) {
    // Flip above the anchor.
    placedTop = anchor.y - size.height;
  } else if (available >= size.height) {
    // No side of the anchor fits, but the menu is short enough to live in the
    // free area: lift it to the bottom of that area.
    placedTop = bottom - size.height;
  } else {
    // Taller than the free area, so no placement fits: pin it to the top of
    // that area and let the list scroll.
    placedTop = top;
    maxHeight = available;
  }

  // Final horizontal clamp, so a menu wider than the viewport or a pointer at
  // the very edge cannot push it off-screen.
  const clampedLeft = Math.max(
    margin,
    Math.min(left, viewport.width - size.width - margin),
  );

  return {
    left: Math.max(0, clampedLeft),
    top: Math.max(0, placedTop),
    maxHeight,
  };
}
