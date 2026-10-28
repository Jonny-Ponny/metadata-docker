import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";

import EditModal from "../EditModal.svelte";

describe("EditModal", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing while hidden", () => {
    render(EditModal, {
      props: { show: false, editingText: "lyrics" },
    });

    expect(screen.queryByText("Edit Unsynchronized Lyrics")).toBeNull();
  });

  it("shows the lyrics and an editable textarea", () => {
    render(EditModal, {
      props: { show: true, editingText: "first line\nsecond line" },
    });

    expect(screen.getByText("Edit Unsynchronized Lyrics")).toBeTruthy();
    expect(
      /** @type {HTMLTextAreaElement} */ (screen.getByRole("textbox")).value,
    ).toBe("first line\nsecond line");
  });

  it("focuses the textarea after opening", async () => {
    render(EditModal, { props: { show: true, editingText: "lyrics" } });

    await vi.advanceTimersByTimeAsync(100);

    expect(document.activeElement).toBe(screen.getByRole("textbox"));
  });

  it("saves the current text", async () => {
    const onSave = vi.fn();
    render(EditModal, {
      props: { show: true, editingText: "old", onSave },
    });

    await fireEvent.input(screen.getByRole("textbox"), {
      target: { value: "updated lyrics" },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(onSave).toHaveBeenCalledWith("updated lyrics");
  });

  it("closes from the close button and the cancel button", async () => {
    const onClose = vi.fn();
    render(EditModal, {
      props: { show: true, editingText: "lyrics", onClose },
    });

    await fireEvent.click(screen.getByTitle("Close"));
    expect(onClose).toHaveBeenCalledTimes(1);

    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("closes on an overlay click but not on a content click", async () => {
    const onClose = vi.fn();
    const { container } = render(EditModal, {
      props: { show: true, editingText: "lyrics", onClose },
    });
    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".modal-overlay")
    );
    const content = /** @type {HTMLElement} */ (
      container.querySelector(".modal-content")
    );

    await fireEvent.click(content);
    expect(onClose).not.toHaveBeenCalled();

    await fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
