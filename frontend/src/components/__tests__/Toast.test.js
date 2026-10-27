import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";

import Toast from "../Toast.svelte";

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the message and the type class", () => {
    render(Toast, { props: { message: "Saved", type: "success" } });

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Saved");
    expect(alert.classList.contains("toast-success")).toBe(true);
  });

  it("defaults to an info toast", () => {
    render(Toast, { props: { message: "Loading" } });

    expect(screen.getByRole("alert").classList.contains("toast-info")).toBe(
      true,
    );
  });

  it("dismisses when the close button is clicked", async () => {
    const onDismiss = vi.fn();
    render(Toast, { props: { message: "Saved", onDismiss } });

    await fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("alert")).toBeNull();
    expect(onDismiss).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(300);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("dismisses automatically after the duration", async () => {
    const onDismiss = vi.fn();
    render(Toast, {
      props: { message: "Saved", duration: 1000, onDismiss },
    });

    await vi.advanceTimersByTimeAsync(999);
    expect(onDismiss).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(301);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
