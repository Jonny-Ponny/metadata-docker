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

  it("closes on Escape from the lyrics textarea", async () => {
    // Escape used to do nothing here: the capture listener that stops the app
    // shortcuts behind the dialog swallowed it too. Every other modal closes
    // on Escape.
    const onClose = vi.fn();
    render(EditModal, {
      props: { show: true, editingText: "lyrics", onClose },
    });

    await fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("lets Tab reach the dialog stack so focus stays inside", async () => {
    // The capture listener swallows every key but Escape, and Tab was caught
    // by it too: the stack's Tab handler never ran, so this dialog had no
    // containment and Tab walked out into the browser chrome.
    render(EditModal, { props: { show: true, editingText: "lyrics" } });
    /** @type {string[]} */
    const reached = [];
    const listener = (/** @type {KeyboardEvent} */ e) => reached.push(e.key);
    // Bubble phase, like the dialog stack: a capture-phase stop would hide it.
    window.addEventListener("keydown", listener);
    try {
      await fireEvent.keyDown(screen.getByRole("textbox"), { key: "Tab" });
    } finally {
      window.removeEventListener("keydown", listener);
    }

    expect(reached).toContain("Tab");
  });

  it("still stops app shortcuts", async () => {
    render(EditModal, { props: { show: true, editingText: "lyrics" } });
    /** @type {string[]} */
    const reached = [];
    const listener = (/** @type {KeyboardEvent} */ e) => reached.push(e.key);
    window.addEventListener("keydown", listener);
    try {
      await fireEvent.keyDown(screen.getByRole("textbox"), { key: "F2" });
      await fireEvent.keyDown(screen.getByRole("textbox"), { key: "Delete" });
    } finally {
      window.removeEventListener("keydown", listener);
    }

    expect(reached).not.toContain("F2");
    expect(reached).not.toContain("Delete");
  });

  it("stops app shortcuts while letting Escape through", async () => {
    // The dialog stops keys in the capture phase so F2/Delete do not fire on
    // the tree behind it, but Escape must still reach the window so the dialog
    // can close.
    const onClose = vi.fn();
    render(EditModal, {
      props: { show: true, editingText: "lyrics", onClose },
    });

    /** @type {string[]} */
    const appSaw = [];
    /** @param {KeyboardEvent} e */
    const listener = (e) => appSaw.push(e.key);
    window.addEventListener("keydown", listener);
    try {
      await fireEvent.keyDown(screen.getByRole("textbox"), { key: "Delete" });
      await fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
    } finally {
      window.removeEventListener("keydown", listener);
    }

    expect(appSaw).not.toContain("Delete");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
