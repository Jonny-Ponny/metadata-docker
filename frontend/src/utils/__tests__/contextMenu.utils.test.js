import { describe, expect, it } from "vitest";

import { placeMenu } from "../contextMenu.utils.js";

/** @type {import("../contextMenu.utils.js").MenuSize} */
const VIEWPORT = { width: 1000, height: 700 };
/** @type {import("../contextMenu.utils.js").MenuSize} */
const MENU = { width: 200, height: 300 };

describe("placeMenu", () => {
  it("opens below and right of the pointer when there is room", () => {
    expect(placeMenu({ x: 100, y: 100 }, MENU, VIEWPORT)).toEqual({
      left: 100,
      top: 100,
      maxHeight: undefined,
    });
  });

  it("flips above the pointer when the menu would overflow the bottom", () => {
    // The reported bug: a row near the bottom opened its menu downwards and
    // ran past the window edge.
    expect(placeMenu({ x: 100, y: 600 }, MENU, VIEWPORT)).toEqual({
      left: 100,
      top: 300,
      maxHeight: undefined,
    });
  });

  it("flips left of the pointer when the menu would overflow the right", () => {
    expect(placeMenu({ x: 950, y: 100 }, MENU, VIEWPORT)).toEqual({
      left: 750,
      top: 100,
      maxHeight: undefined,
    });
  });

  it("keeps a menu taller than the window inside it", () => {
    // Flipping cannot help here: the menu is taller than the viewport, so it
    // has to be capped rather than pushed up and out of the window.
    const tall = { width: 200, height: 900 };
    const placement = placeMenu({ x: 100, y: 400 }, tall, VIEWPORT);

    expect(placement.top).toBe(8);
    expect(placement.maxHeight).toBe(684);
    expect(
      placement.top + /** @type {number} */ (placement.maxHeight),
    ).toBeLessThanOrEqual(VIEWPORT.height);
  });

  it("flips up when the menu fits above but not below", () => {
    const tall = { width: 200, height: 500 };
    const placement = placeMenu({ x: 100, y: 620 }, tall, VIEWPORT);

    // 620 + 500 is past the bottom, 620 - 500 is still on screen.
    expect(placement.top).toBe(120);
    expect(placement.maxHeight).toBeUndefined();
  });

  it("never places the menu outside the window", () => {
    const placement = placeMenu(
      { x: 990, y: 690 },
      { width: 999, height: 20 },
      VIEWPORT,
    );

    expect(placement.left).toBeGreaterThanOrEqual(8);
    expect(placement.top).toBeGreaterThanOrEqual(8);
    expect(placement.left + MENU.width).toBeLessThan(VIEWPORT.width + 999);
  });

  it("uses the margin when the pointer sits on the edge", () => {
    expect(placeMenu({ x: 2, y: 2 }, MENU, VIEWPORT)).toMatchObject({
      left: 8,
      top: 8,
    });
  });
});
