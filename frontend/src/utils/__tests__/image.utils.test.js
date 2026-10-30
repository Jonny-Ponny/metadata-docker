import { describe, expect, it } from "vitest";

import { formatImageDimensions } from "../image.utils.js";

describe("image utils", () => {
  it("formats natural image dimensions", () => {
    expect(formatImageDimensions(1234, 1234)).toBe("1234x1234px");
    expect(formatImageDimensions(600, 450)).toBe("600x450px");
  });

  it.each([
    [0, 0],
    [0, 450],
    [600, -1],
    [Number.NaN, 450],
    [600, Number.POSITIVE_INFINITY],
  ])("returns null for invalid dimensions (%sx%s)", (width, height) => {
    expect(formatImageDimensions(width, height)).toBeNull();
  });
});
