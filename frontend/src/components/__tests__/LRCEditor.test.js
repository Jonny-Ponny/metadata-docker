import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";
import { get } from "svelte/store";

import LRCEditor from "../LRCEditor.svelte";
import { toast } from "../../stores/toast.store.js";

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

/**
 * Answer the modal's "get-current-time" round trip.
 * @param {number} time
 */
function answerWithTime(time) {
  /** @param {Event} event */
  const handler = (event) => {
    const detail =
      /** @type {CustomEvent<{ callback: (time: number) => void }>} */ (event)
        .detail;
    detail.callback(time);
  };
  window.addEventListener("get-current-time", handler);
  return () => window.removeEventListener("get-current-time", handler);
}

/**
 * @param {string} text
 * @param {string} [name]
 */
function lyricFile(text, name = "import.lrc") {
  return new File([text], name, { type: "text/plain" });
}

/**
 * @param {HTMLElement} input
 * @param {File} file
 */
async function selectFile(input, file) {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: [file],
  });
  await fireEvent.change(input);
}

const baseProps = {
  isOpen: true,
  onClose: () => {},
  initialLyrics: "first line\nsecond line",
  initialTimestamps: ["[00:05.00]", "[00:10.00]"],
};

describe("LRCEditor", () => {
  /** @type {(() => void) | undefined} */
  let stopTime;

  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn(() => 1),
    );
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    stopTime?.();
    stopTime = undefined;
    delete (/** @type {any} */ (Element.prototype).scrollIntoView);
    vi.unstubAllGlobals();
    toast.clear();
  });

  it("renders nothing while closed", () => {
    render(LRCEditor, { props: { ...baseProps, isOpen: false } });

    expect(screen.queryByText("Synced Lyrics Editor")).toBeNull();
  });

  it("lays out the timestamps, lyrics and synchronized columns", () => {
    render(LRCEditor, { props: baseProps });

    expect(screen.getByText("Synced Lyrics Editor")).toBeTruthy();
    expect(screen.getByText("Timestamps")).toBeTruthy();
    expect(screen.getByText("Unsynchronized lyrics")).toBeTruthy();
    expect(screen.getByText("Synchronized lyrics")).toBeTruthy();
    expect(screen.getAllByText("[00:05.00]").length).toBeGreaterThan(0);
    expect(screen.getAllByText("first line").length).toBeGreaterThan(0);
    expect(screen.getAllByText("second line").length).toBeGreaterThan(0);
  });

  it("parses timestamps out of the initial lyrics text", () => {
    render(LRCEditor, {
      props: {
        isOpen: true,
        initialLyrics: "[00:01.00]one\nplain line",
      },
    });

    expect(screen.getAllByText("one").length).toBeGreaterThan(0);
    expect(screen.getAllByText("plain line").length).toBeGreaterThan(0);
    expect(screen.getAllByText("[00:01.00]").length).toBeGreaterThan(0);
    expect(screen.getAllByText("[--:--.--]").length).toBeGreaterThan(0);
  });

  it("saves synchronized lyrics with their timestamps", async () => {
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(LRCEditor, { props: { ...baseProps, onSave, onClose } });

    await fireEvent.click(screen.getByRole("button", { name: "Save to File" }));

    expect(onSave).toHaveBeenCalledWith({
      lyrics: "first line\nsecond line",
      timestamps: ["[00:05.00]", "[00:10.00]"],
      synchronizedLyrics: "[00:05.00] first line\n[00:10.00] second line",
      hasTimestamps: true,
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("saves plain lyrics without an LRC string", async () => {
    const onSave = vi.fn();
    render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "just words", onSave },
    });

    await fireEvent.click(screen.getByRole("button", { name: "Save to File" }));

    expect(onSave).toHaveBeenCalledWith({
      lyrics: "just words",
      timestamps: ["[--:--.--]"],
      synchronizedLyrics: null,
      hasTimestamps: false,
    });
  });

  it("seeks the player from a timestamped line", async () => {
    render(LRCEditor, { props: baseProps });
    const seek = vi.fn();
    window.addEventListener("lyrics-seek", seek);

    const line = /** @type {HTMLElement} */ (
      document.getElementById("modal-line-1")
    );
    await fireEvent.click(line);

    const event = /** @type {CustomEvent<{ time: number }>} */ (
      seek.mock.calls[0][0]
    );
    expect(event.detail.time).toBe(10);
    window.removeEventListener("lyrics-seek", seek);
  });

  it("does not seek from an untimed line", async () => {
    render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "no timing" },
    });
    const seek = vi.fn();
    window.addEventListener("lyrics-seek", seek);

    const line = /** @type {HTMLElement} */ (
      document.getElementById("modal-line-0")
    );
    await fireEvent.click(line);

    expect(seek).not.toHaveBeenCalled();
    window.removeEventListener("lyrics-seek", seek);
  });

  it("edits the lyrics and keeps the timestamps", async () => {
    const onSave = vi.fn();
    render(LRCEditor, { props: { ...baseProps, onSave } });

    await fireEvent.click(screen.getByTitle("Edit lyrics"));
    const textarea = screen.getByPlaceholderText(/Enter lyrics here/);
    await fireEvent.input(textarea, {
      target: { value: "[00:02.00]rewritten\nadded line" },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    await tick();

    expect(screen.getAllByText("rewritten").length).toBeGreaterThan(0);
    expect(screen.getAllByText("added line").length).toBeGreaterThan(0);

    await fireEvent.click(screen.getByRole("button", { name: "Save to File" }));
    expect(onSave).toHaveBeenCalledWith({
      lyrics: "rewritten\nadded line",
      timestamps: ["[00:02.00]", "[--:--.--]"],
      synchronizedLyrics: "[00:02.00] rewritten\nadded line",
      hasTimestamps: true,
    });
  });

  it("fills the first timestamp from the current playback time", async () => {
    stopTime = answerWithTime(12.5);
    render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "one\ntwo" },
    });
    const editButtons = screen.getAllByTitle("Edit timestamp");

    await fireEvent.click(editButtons[0]);
    await tick();

    const input = document.querySelector(".timestamp-input");
    expect(/** @type {HTMLInputElement} */ (input).value).toBe("00:12.50");
  });

  it("saves a timestamp from the edit modal", async () => {
    render(LRCEditor, { props: baseProps });
    const editButtons = screen.getAllByTitle("Edit timestamp");

    await fireEvent.click(editButtons[0]);
    await tick();

    const input = /** @type {HTMLElement} */ (
      document.querySelector(".timestamp-input")
    );
    await fireEvent.input(input, { target: { value: "00:03.00" } });
    await tick();
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Timestamp" }),
    );

    await waitFor(() =>
      expect(screen.getAllByText("[00:03.00]").length).toBeGreaterThan(0),
    );
  });

  it("clears every timestamp", async () => {
    render(LRCEditor, { props: baseProps });

    await fireEvent.click(screen.getByTitle("Clear all timestamps"));

    await waitFor(() => expect(screen.queryByText("[00:05.00]")).toBeNull());
    expect(screen.getAllByText("[--:--.--]").length).toBeGreaterThan(0);
    expect(get(toast).at(-1)?.message).toBe("All timestamps cleared");
  });

  it("shifts all timestamps later and earlier", async () => {
    render(LRCEditor, { props: baseProps });
    const amount = screen.getByLabelText("Shift amount in seconds");

    await fireEvent.input(amount, { target: { value: "1.5" } });
    await fireEvent.click(screen.getByLabelText("Shift all timestamps later"));

    await waitFor(() =>
      expect(screen.getAllByText("[00:06.50]").length).toBeGreaterThan(0),
    );
    expect(get(toast).at(-1)?.message).toBe("Shifted 2 timestamps by +1.50s");

    await fireEvent.click(
      screen.getByLabelText("Shift all timestamps earlier"),
    );

    await waitFor(() =>
      expect(screen.getAllByText("[00:05.00]").length).toBeGreaterThan(0),
    );
    expect(get(toast).at(-1)?.message).toBe("Shifted 2 timestamps by -1.50s");
  });

  it("rejects a shift past the start of the song", async () => {
    render(LRCEditor, { props: baseProps });

    await fireEvent.input(screen.getByLabelText("Shift amount in seconds"), {
      target: { value: "30" },
    });
    await fireEvent.click(
      screen.getByLabelText("Shift all timestamps earlier"),
    );

    expect(get(toast).at(-1)?.message).toBe(
      "Cannot shift earlier than 00:00.00 (max -5.00s)",
    );
    expect(screen.getAllByText("[00:05.00]").length).toBeGreaterThan(0);
  });

  it("rejects a zero shift amount", async () => {
    render(LRCEditor, { props: baseProps });

    await fireEvent.input(screen.getByLabelText("Shift amount in seconds"), {
      target: { value: "0" },
    });
    await fireEvent.click(screen.getByLabelText("Shift all timestamps later"));

    expect(get(toast).at(-1)?.message).toBe("Enter a non-zero shift amount");
  });

  it("imports an .lrc file", async () => {
    const { container } = render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "" },
    });
    const fileInput = /** @type {HTMLInputElement} */ (
      container.querySelector(".hidden-file-input")
    );

    await selectFile(fileInput, lyricFile("[00:03.00]imported line"));

    await waitFor(() =>
      expect(screen.getAllByText("imported line").length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText("[00:03.00]").length).toBeGreaterThan(0);
    expect(get(toast).at(-1)?.message).toBe("Imported lyrics from import.lrc");
  });

  it("reports an .lrc file without lyrics", async () => {
    const { container } = render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "" },
    });
    const fileInput = /** @type {HTMLInputElement} */ (
      container.querySelector(".hidden-file-input")
    );

    await selectFile(fileInput, lyricFile("[ar:Artist]"));

    expect(get(toast).at(-1)?.message).toBe(
      "No lyrics found in the selected file",
    );
  });

  it("exports the lyrics as an .lrc download", async () => {
    const createObjectURL = vi.fn((/** @type {Blob} */ _blob) => "blob:lrc");
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(LRCEditor, {
      props: {
        ...baseProps,
        trackInfo: { title: "Song", artist: "Artist", album: "Album" },
      },
    });

    await fireEvent.click(screen.getByRole("button", { name: /export/i }));

    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = /** @type {Blob} */ (createObjectURL.mock.calls[0][0]);
    expect(await blob.text()).toBe(
      "[ti:Song]\n[ar:Artist]\n[al:Album]\n[00:05.00] first line\n[00:10.00] second line",
    );
    expect(get(toast).at(-1)?.message).toBe("LRC file downloaded");
  });

  it("refuses to export empty lyrics", async () => {
    render(LRCEditor, { props: { isOpen: true, initialLyrics: "" } });

    await fireEvent.click(screen.getByRole("button", { name: /export/i }));

    expect(get(toast).at(-1)?.message).toBe("No lyrics to export");
  });

  it("copies the LRC and the plain lyrics", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(LRCEditor, { props: baseProps });

    await fireEvent.click(screen.getByRole("button", { name: /copy lrc/i }));

    expect(writeText).toHaveBeenCalledWith(
      "[00:05.00] first line\n[00:10.00] second line",
    );
    expect(get(toast).at(-1)?.message).toBe("Lyrics copied to clipboard");

    await fireEvent.click(screen.getByRole("button", { name: /copy text/i }));

    expect(writeText).toHaveBeenLastCalledWith("first line\nsecond line");
    expect(get(toast).at(-1)?.message).toBe(
      "Unsynced lyrics copied to clipboard",
    );
  });

  it("marks the active line from player time updates", async () => {
    render(LRCEditor, { props: baseProps });

    window.dispatchEvent(
      new CustomEvent("player-time-update", { detail: { time: 6 } }),
    );
    await tick();

    expect(
      /** @type {HTMLElement} */ (document.getElementById("modal-line-0"))
        .className,
    ).toContain("playing");
    expect(
      /** @type {HTMLElement} */ (document.getElementById("modal-line-1"))
        .className,
    ).not.toContain("playing");
  });

  it("synchronizes the next line from the current playback time", async () => {
    stopTime = answerWithTime(7);
    render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "one\ntwo" },
    });

    await fireEvent.keyDown(document.body, { key: "s" });
    await tick();

    await waitFor(() =>
      expect(screen.getAllByText("[00:07.00]").length).toBeGreaterThan(0),
    );
  });

  it("uses the live player time for the current-line shortcut", async () => {
    render(LRCEditor, {
      props: {
        isOpen: true,
        initialLyrics: "one\ntwo",
        initialTimestamps: ["[00:05.00]", "[00:10.00]"],
      },
    });

    // Make line 0 active from a stale timeupdate value.
    window.dispatchEvent(
      new CustomEvent("player-time-update", { detail: { time: 6 } }),
    );
    await tick();

    // The player answers with the live value, not the stored 6.
    stopTime = answerWithTime(7);
    await fireEvent.keyDown(document.body, { key: "c" });
    await tick();

    await waitFor(() =>
      expect(screen.getAllByText("[00:07.00]").length).toBeGreaterThan(0),
    );
  });

  it("warns when there is no active line to synchronize", async () => {
    render(LRCEditor, {
      props: { isOpen: true, initialLyrics: "one\ntwo" },
    });

    await fireEvent.keyDown(screen.getByText("Synced Lyrics Editor"), {
      key: "c",
    });

    expect(get(toast).at(-1)?.message).toBe("No active line to set timestamp");
  });

  it("closes from the overlay, header button and cancel button", async () => {
    const onClose = vi.fn();
    const { container } = render(LRCEditor, {
      props: { ...baseProps, onClose },
    });

    await fireEvent.click(screen.getByTitle("Close"));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".lyrics-modal-overlay")
    );
    await fireEvent.click(overlay);

    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("does not close when the dialog body is clicked", async () => {
    const onClose = vi.fn();
    const { container } = render(LRCEditor, {
      props: { ...baseProps, onClose },
    });

    const dialog = /** @type {HTMLElement} */ (
      container.querySelector(".lyrics-modal")
    );
    await fireEvent.click(dialog);

    expect(onClose).not.toHaveBeenCalled();
  });
});
