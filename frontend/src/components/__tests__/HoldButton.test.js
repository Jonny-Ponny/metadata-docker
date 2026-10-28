import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";
import { createRawSnippet } from "svelte";

import HoldButton from "../HoldButton.svelte";

const children = createRawSnippet(() => ({
  render: () => "<span>Delete</span>",
}));

describe("HoldButton", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders its content as an enabled button", () => {
    render(HoldButton, { props: { children, title: "Delete file" } });

    const button = screen.getByRole("button", { name: "Delete" });
    expect(button.getAttribute("title")).toBe("Delete file");
    expect(button.getAttribute("aria-disabled")).toBe("false");
  });

  it("confirms after a full hold", async () => {
    const onConfirm = vi.fn();
    render(HoldButton, {
      props: { children, duration: 500, onConfirm },
    });

    const button = screen.getByRole("button", { name: "Delete" });
    await fireEvent.mouseDown(button);
    expect(button.classList.contains("holding")).toBe(true);

    await vi.advanceTimersByTimeAsync(500);

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("cancels when the pointer is released early", async () => {
    const onConfirm = vi.fn();
    render(HoldButton, {
      props: { children, duration: 500, onConfirm },
    });

    const button = screen.getByRole("button", { name: "Delete" });
    await fireEvent.mouseDown(button);
    await vi.advanceTimersByTimeAsync(300);
    await fireEvent.mouseUp(button);
    await vi.advanceTimersByTimeAsync(500);

    expect(onConfirm).not.toHaveBeenCalled();
    expect(button.classList.contains("holding")).toBe(false);
  });

  it("exposes the disabled state", () => {
    render(HoldButton, { props: { children, disabled: true } });

    const button = screen.getByRole("button", { name: "Delete" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.classList.contains("disabled")).toBe(true);
  });
});
