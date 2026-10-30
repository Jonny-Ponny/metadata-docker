import { afterEach, describe, expect, it, vi } from "vitest";

import { formatImageDimensions, probeImageSize } from "../image.utils.js";

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

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads dimensions from a detached image before it is attached", async () => {
    class ProbeImage {
      naturalWidth = 640;
      naturalHeight = 480;
      /** @type {(() => void) | null} */
      onload = null;
      /** @type {((event: Event) => void) | null} */
      onerror = null;

      /** @param {string} _value */
      set src(_value) {
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal("Image", ProbeImage);

    await expect(probeImageSize("blob:cover")).resolves.toEqual({
      width: 640,
      height: 480,
    });
  });

  it("returns null when the detached image cannot load", async () => {
    class ProbeImage {
      naturalWidth = 0;
      naturalHeight = 0;
      /** @type {(() => void) | null} */
      onload = null;
      /** @type {((event: Event) => void) | null} */
      onerror = null;

      /** @param {string} _value */
      set src(_value) {
        queueMicrotask(() => this.onerror?.(new Event("error")));
      }
    }
    vi.stubGlobal("Image", ProbeImage);

    await expect(probeImageSize("blob:missing")).resolves.toBeNull();
  });

  it("returns null for an image without intrinsic dimensions", async () => {
    class ProbeImage {
      naturalWidth = 0;
      naturalHeight = 0;
      /** @type {(() => void) | null} */
      onload = null;
      /** @type {((event: Event) => void) | null} */
      onerror = null;

      /** @param {string} _value */
      set src(_value) {
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal("Image", ProbeImage);

    await expect(probeImageSize("blob:empty")).resolves.toBeNull();
  });
});
