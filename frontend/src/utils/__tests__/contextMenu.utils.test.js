import { describe, expect, it } from "vitest";

import { placeMenu } from "../contextMenu.utils.js";

/** @type {import("../contextMenu.utils.js").MenuSize} */
const VIEWPORT = { width: 1000, height: 700 };
/** @type {import("../contextMenu.utils.js").MenuSize} */
const MENU = { width: 200, height: 300 };
/** The player bar is fixed to the bottom; menus must stay above it. */
const PLAYER = 70;

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

  it("keeps the menu off the left edge when the pointer sits on it", () => {
    // The menu still hangs from the pointer vertically (there is room below);
    // only the horizontal position needs the margin.
    expect(placeMenu({ x: 2, y: 2 }, MENU, VIEWPORT)).toMatchObject({
      left: 8,
      top: 2,
    });
  });

  describe("with the player bar at the bottom", () => {
    /** @type {import("../contextMenu.utils.js").Viewport} */
    const withPlayer = { ...VIEWPORT, bottom: PLAYER };

    it("flips above a row hidden behind the player", () => {
      // 640 + 300 would land the menu's bottom past the window; 640 is already
      // inside the player bar. Either way the menu belongs above the row.
      const placement = placeMenu({ x: 100, y: 640 }, MENU, withPlayer);

      // Flips above the row and stops just clear of the player bar.
      expect(placement.top).toBe(VIEWPORT.height - PLAYER - 8 - MENU.height);
      expect(placement.top + MENU.height).toBeLessThanOrEqual(
        VIEWPORT.height - PLAYER,
      );
    });

    it("never places the menu over the player", () => {
      const placement = placeMenu({ x: 100, y: 500 }, MENU, withPlayer);

      expect(placement.top + MENU.height).toBeLessThanOrEqual(
        VIEWPORT.height - PLAYER,
      );
    });

    it("never overlaps the player for any anchor or menu size", () => {
      // A sweep instead of hand-picked cases: the earlier fixes each closed one
      // hole and opened another (an anchor behind the player, a menu exactly
      // the free height, a flip that still landed under the bar).
      /** @type {string[]} */
      const failures = [];
      const freeBottom = VIEWPORT.height - PLAYER;
      for (let y = 0; y <= VIEWPORT.height; y += 10) {
        for (const height of [50, 200, 300, 615, 650, 900]) {
          for (const x of [5, 500, 995]) {
            const placement = placeMenu(
              { x, y },
              { width: MENU.width, height },
              withPlayer,
            );
            const placedHeight =
              placement.maxHeight === undefined
                ? height
                : Math.min(height, placement.maxHeight);
            const label = `y=${y} h=${height} x=${x} -> ${JSON.stringify(placement)}`;
            if (placement.top < 0) failures.push(`above the window: ${label}`);
            if (placement.top + placedHeight > freeBottom) {
              failures.push(`over the player: ${label}`);
            }
            if (placement.left < 0)
              failures.push(`left of the window: ${label}`);
            if (placement.left + MENU.width > VIEWPORT.width) {
              failures.push(`right of the window: ${label}`);
            }
          }
        }
      }

      expect(failures).toEqual([]);
    });

    it("caps a menu taller than the space above the player", () => {
      const tall = { width: 200, height: 900 };
      const placement = placeMenu({ x: 100, y: 300 }, tall, withPlayer);

      expect(placement.top).toBe(8);
      expect(placement.maxHeight).toBe(VIEWPORT.height - PLAYER - 16);
      expect(
        placement.top + /** @type {number} */ (placement.maxHeight),
      ).toBeLessThanOrEqual(VIEWPORT.height - PLAYER);
    });
  });
});
