import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import { createToastStore, toast } from "../toast.store.js";

describe("toast store", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    toast.clear();
  });

  it("shows and auto-removes a toast", () => {
    const store = createToastStore();
    const seen = vi.fn();
    const unsubscribe = store.subscribe(seen);

    const id = store.show("Hello", "info", 1000);

    expect(get(store)).toHaveLength(1);
    expect(get(store)[0]).toMatchObject({
      id,
      message: "Hello",
      type: "info",
      duration: 1000,
    });

    vi.advanceTimersByTime(999);
    expect(get(store)).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(get(store)).toHaveLength(0);
    expect(seen).toHaveBeenCalled();

    unsubscribe();
  });

  it("uses the typed helpers", () => {
    const store = createToastStore();

    store.success("Saved");
    store.error("Broke");
    store.warning("Careful");
    store.info("FYI");

    expect(get(store).map((item) => item.type)).toEqual([
      "success",
      "error",
      "warning",
      "info",
    ]);
    expect(get(store).map((item) => item.duration)).toEqual([
      5000, 5000, 5000, 5000,
    ]);
  });

  it("appends a custom duration", () => {
    const store = createToastStore();

    store.success("Short", 1500);

    expect(get(store)[0].duration).toBe(1500);
  });

  it("removes a single toast by id", () => {
    const store = createToastStore();
    const first = store.success("One");
    store.error("Two");

    store.remove(first);

    expect(get(store)).toHaveLength(1);
    expect(get(store)[0].message).toBe("Two");
  });

  it("clears every toast", () => {
    const store = createToastStore();
    store.success("One");
    store.error("Two");

    store.clear();

    expect(get(store)).toEqual([]);
  });

  it("stops notifying after unsubscribe", () => {
    const store = createToastStore();
    const seen = vi.fn();
    const unsubscribe = store.subscribe(seen);
    seen.mockClear();

    unsubscribe();
    store.info("ignored");

    expect(seen).not.toHaveBeenCalled();
  });

  it("exposes a singleton store", () => {
    expect(typeof toast.success).toBe("function");
    expect(get(toast)).toEqual([]);
  });
});
