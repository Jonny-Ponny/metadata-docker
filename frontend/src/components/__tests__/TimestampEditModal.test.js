import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";
import { tick } from "svelte";

import TimestampEditModal from "../TimestampEditModal.svelte";

const timestamps = ["[00:10.00]", "[00:15.00]", "[00:20.00]"];

describe("TimestampEditModal", () => {
  it("renders nothing while hidden", () => {
    render(TimestampEditModal, { props: { show: false } });

    expect(screen.queryByText(/Edit Timestamp/)).toBeNull();
  });

  it("prefills the current value and shows the allowed range", () => {
    render(TimestampEditModal, {
      props: {
        show: true,
        lineIndex: 1,
        currentValue: "00:15.00",
        timestamps,
      },
    });

    expect(screen.getByText("Edit Timestamp for Line 2")).toBeTruthy();
    expect(
      /** @type {HTMLInputElement} */ (screen.getByRole("textbox")).value,
    ).toBe("00:15.00");
    expect(screen.getByText("Between [00:10.00] and [00:20.00]")).toBeTruthy();
  });

  it("shows the end of the song as the upper bound for the last line", () => {
    render(TimestampEditModal, {
      props: {
        show: true,
        lineIndex: 2,
        currentValue: "00:20.00",
        timestamps,
      },
    });

    expect(screen.getByText("Between [00:15.00] and end of song")).toBeTruthy();
  });

  it("saves a valid timestamp", async () => {
    const onSave = vi.fn();
    render(TimestampEditModal, {
      props: {
        show: true,
        lineIndex: 1,
        currentValue: "00:15.00",
        timestamps,
        onSave,
      },
    });

    await fireEvent.input(screen.getByRole("textbox"), {
      target: { value: "00:18.50" },
    });
    await tick();
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Timestamp" }),
    );

    expect(onSave).toHaveBeenCalledWith(1, "00:18.50");
    expect(screen.queryByText(/Invalid format/)).toBeNull();
  });

  it("rejects a malformed timestamp", async () => {
    const onSave = vi.fn();
    render(TimestampEditModal, {
      props: { show: true, lineIndex: 1, timestamps, onSave },
    });

    await fireEvent.input(screen.getByRole("textbox"), {
      target: { value: "1234" },
    });
    await tick();
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Timestamp" }),
    );

    expect(
      screen.getByText("Invalid format. Use MM:SS.ss (e.g., 01:23.45)"),
    ).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("clamps seconds above 59 while typing", async () => {
    render(TimestampEditModal, {
      props: { show: true, lineIndex: 1, timestamps },
    });

    await fireEvent.input(screen.getByRole("textbox"), {
      target: { value: "00:99.00" },
    });
    await tick();

    expect(
      /** @type {HTMLInputElement} */ (screen.getByRole("textbox")).value,
    ).toBe("00:59.00");
  });

  it("rejects a timestamp before the previous line", async () => {
    const onSave = vi.fn();
    render(TimestampEditModal, {
      props: { show: true, lineIndex: 2, timestamps, onSave },
    });

    await fireEvent.input(screen.getByRole("textbox"), {
      target: { value: "00:12.00" },
    });
    await tick();
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Timestamp" }),
    );

    expect(screen.getByText("Must be after [00:15.00]")).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("fills in the current playback time", async () => {
    render(TimestampEditModal, {
      props: {
        show: true,
        lineIndex: 1,
        timestamps,
        currentTime: 75.5,
      },
    });

    await fireEvent.click(
      screen.getByRole("button", { name: /use current playback time/i }),
    );

    expect(
      /** @type {HTMLInputElement} */ (screen.getByRole("textbox")).value,
    ).toBe("01:15.50");
  });

  it("formats digits while typing", async () => {
    render(TimestampEditModal, {
      props: { show: true, lineIndex: 1, timestamps },
    });

    await fireEvent.input(screen.getByRole("textbox"), {
      target: { value: "011234" },
    });
    await tick();

    expect(
      /** @type {HTMLInputElement} */ (screen.getByRole("textbox")).value,
    ).toBe("01:12.34");
  });

  it("saves on Enter and closes on Escape", async () => {
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(TimestampEditModal, {
      props: {
        show: true,
        lineIndex: 1,
        currentValue: "00:15.00",
        timestamps,
        onSave,
        onClose,
      },
    });
    await tick();
    const input = screen.getByRole("textbox");

    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith(1, "00:15.00");

    await fireEvent.keyDown(input, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes from the overlay, close button and cancel button", async () => {
    const onClose = vi.fn();
    const { container } = render(TimestampEditModal, {
      props: { show: true, lineIndex: 1, timestamps, onClose },
    });
    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".modal-overlay")
    );

    await fireEvent.click(screen.getByTitle("Close"));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await fireEvent.click(overlay);

    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
