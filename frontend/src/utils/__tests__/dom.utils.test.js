import { afterEach, describe, expect, it, vi } from "vitest";

import {
  debounce,
  downloadTextFile,
  equalizeElementHeights,
  scrollToElement,
} from "../dom.utils.js";

describe("dom utils", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("debounces calls to the trailing edge", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const debounced = debounce(fn, 100);

    debounced("a");
    debounced("b");
    debounced("c");

    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(99);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("c");
  });

  it("scrolls with the default options", () => {
    const element = document.createElement("div");
    const scrollIntoView = vi.fn();
    element.scrollIntoView = scrollIntoView;

    scrollToElement(element);

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    });
  });

  it("passes custom scroll options through", () => {
    const element = document.createElement("div");
    const scrollIntoView = vi.fn();
    element.scrollIntoView = scrollIntoView;

    scrollToElement(element, { behavior: "auto", block: "start" });

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "auto",
      block: "start",
      inline: "nearest",
    });
  });

  it("creates, clicks and cleans up a download link", async () => {
    const createObjectURL = vi.fn(
      (/** @type {Blob} */ _blob) => "blob:download",
    );
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    const filename = "lyrics.lrc";
    downloadTextFile(filename, "line one\nline two", "text/plain");

    const blob = /** @type {Blob} */ (createObjectURL.mock.calls[0][0]);
    expect(blob.type).toBe("text/plain");
    expect(await blob.text()).toBe("line one\nline two");
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:download");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("equalizes the height of every element", () => {
    const first = document.createElement("div");
    const second = document.createElement("div");
    Object.defineProperty(first, "scrollHeight", { value: 40 });
    Object.defineProperty(second, "scrollHeight", { value: 60 });

    const max = equalizeElementHeights([first, second]);

    expect(max).toBe(60);
    expect(first.style.minHeight).toBe("60px");
    expect(second.style.height).toBe("60px");
  });

  it("ignores empty element lists", () => {
    expect(equalizeElementHeights([])).toBe(0);
  });
});
