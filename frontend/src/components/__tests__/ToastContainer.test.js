import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";

import ToastContainer from "../ToastContainer.svelte";
import { toast } from "../../stores/toast.store.js";

describe("ToastContainer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    toast.clear();
  });

  afterEach(() => {
    toast.clear();
    vi.useRealTimers();
  });

  it("renders nothing without toasts", () => {
    const { container } = render(ToastContainer);

    expect(container.querySelector(".toast-container")).toBeNull();
  });

  it("renders toasts pushed to the store, newest last", async () => {
    render(ToastContainer);

    toast.success("First");
    toast.error("Second");
    await vi.advanceTimersByTimeAsync(0);

    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(2);
    expect(alerts[0].textContent).toContain("First");
    expect(alerts[0].classList.contains("toast-success")).toBe(true);
    expect(alerts[1].textContent).toContain("Second");
    expect(alerts[1].classList.contains("toast-error")).toBe(true);
  });

  it("removes a toast when its close button is clicked", async () => {
    render(ToastContainer);

    toast.info("Dismiss me");
    await vi.advanceTimersByTimeAsync(0);

    await fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("removes every toast when cleared", async () => {
    render(ToastContainer);

    toast.success("One");
    toast.warning("Two");
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.getAllByRole("alert")).toHaveLength(2);

    toast.clear();
    await vi.advanceTimersByTimeAsync(0);

    expect(screen.queryByRole("alert")).toBeNull();
  });
});
