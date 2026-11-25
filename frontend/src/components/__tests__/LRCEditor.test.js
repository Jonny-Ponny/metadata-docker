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
 * The class list of the row that renders a lyric line, which carries the
 * playing and selected state for the timestamp cell and the text together.
 * @param {number} index
 */
function rowClass(index) {
  return (
    document.getElementById(`modal-line-${index}`)?.closest(".lyric-row")
      ?.className ?? ""
  );
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

  it("closes on Escape, including from a focused field", async () => {
    const onClose = vi.fn();
    render(LRCEditor, { props: { ...baseProps, onClose } });

    // An unfocused target: the modal reacts wherever the key is pressed.
    await fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    // And from a textarea, where S/C are ignored but Escape still closes.
    const field = document.querySelector("textarea");
    if (field) await fireEvent.keyDown(field, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(field ? 2 : 1);
  });

  it("closes only the inner edit dialog on Escape", async () => {
    // Opening "Edit lyrics" stacks a dialog over the editor. Both listen for
    // Escape, so one keypress used to close the editor as well.
    const onClose = vi.fn();
    render(LRCEditor, { props: { ...baseProps, onClose } });

    await fireEvent.click(screen.getByTitle("Edit lyrics"));
    const inner = await screen.findByRole("dialog", {
      name: "Edit unsynchronized lyrics",
    });

    await fireEvent.keyDown(inner, { key: "Escape" });

    expect(
      screen.queryByRole("dialog", { name: "Edit unsynchronized lyrics" }),
    ).toBeNull();
    // The editor itself is still open.
    expect(onClose).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Synced lyrics editor" }),
    ).toBeTruthy();
  });

  it("makes the editor inert while its text dialog is open", async () => {
    // The text dialog renders as a sibling of the editor, not inside it, so
    // without inert the browser's tab order walked out of the dialog and into
    // the editor underneath.
    render(LRCEditor, { props: { ...baseProps, onClose: vi.fn() } });
    const editorOverlay = /** @type {HTMLElement} */ (
      document.querySelector(".lyrics-modal-overlay")
    );
    expect(editorOverlay.inert).toBeFalsy();

    await fireEvent.click(screen.getByTitle("Edit lyrics"));
    await screen.findByRole("dialog", {
      name: "Edit unsynchronized lyrics",
    });

    expect(editorOverlay.inert).toBe(true);
    expect(
      /** @type {HTMLElement} */ (document.querySelector(".modal-overlay"))
        .inert,
    ).toBeFalsy();
  });

  it("lays out a timestamp column beside the lyrics", () => {
    render(LRCEditor, { props: baseProps });

    expect(screen.getByText("Synced Lyrics Editor")).toBeTruthy();
    expect(screen.getByText("Timestamps")).toBeTruthy();
    expect(screen.getByText("Lyrics")).toBeTruthy();
    // Each line is one row with its timestamp and text, so the timestamp is
    // shown once per line instead of in a separate synchronized column.
    expect(screen.queryByText("Synchronized lyrics")).toBeNull();
    expect(screen.getAllByText("[00:05.00]")).toHaveLength(1);
    expect(screen.getAllByText("first line")).toHaveLength(1);
    expect(screen.getAllByText("second line")).toHaveLength(1);
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
    // The untimed line cannot be jumped to.
    expect(
      /** @type {HTMLButtonElement} */ (
        document.getElementById("modal-timestamp-1")
      ).disabled,
    ).toBe(true);
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

    const timestamp = /** @type {HTMLElement} */ (
      document.getElementById("modal-timestamp-1")
    );
    await fireEvent.click(timestamp);

    const event = /** @type {CustomEvent<{ time: number }>} */ (
      seek.mock.calls[0][0]
    );
    expect(event.detail.time).toBe(10);
    window.removeEventListener("lyrics-seek", seek);
  });

  it("only selects when the lyric text is clicked, so ranges do not seek", async () => {
    render(LRCEditor, { props: baseProps });
    const seek = vi.fn();
    window.addEventListener("lyrics-seek", seek);

    await fireEvent.click(
      /** @type {HTMLElement} */ (
        document.querySelector("#modal-line-1 [role=button]")
      ),
    );
    expect(seek).not.toHaveBeenCalled();

    const row = /** @type {HTMLElement} */ (
      document.querySelectorAll(".lyric-row")[1]
    );
    expect(row.className).toContain("selected");
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

    expect(rowClass(0)).toContain("playing");
    expect(rowClass(1)).not.toContain("playing");
  });

  it("moves the active line past an untimed line", async () => {
    render(LRCEditor, {
      props: {
        isOpen: true,
        initialLyrics: "[00:10.00]first\n\n[00:20.00]next",
      },
    });

    window.dispatchEvent(
      new CustomEvent("player-time-update", { detail: { time: 25 } }),
    );
    await tick();

    // The blank line is stored as a placeholder. It must not pin the
    // highlight to the line before it.
    expect(rowClass(1)).not.toContain("playing");
    expect(rowClass(2)).toContain("playing");
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

  it("keeps the current line in view when syncing with the c shortcut", async () => {
    render(LRCEditor, {
      props: {
        isOpen: true,
        initialLyrics: "one\ntwo",
        initialTimestamps: ["[00:05.00]", "[00:10.00]"],
      },
    });

    // Make line 0 the active line.
    window.dispatchEvent(
      new CustomEvent("player-time-update", { detail: { time: 6 } }),
    );
    await tick();

    stopTime = answerWithTime(7);
    await fireEvent.keyDown(document.body, { key: "c" });
    await tick();

    // The synced line is scrolled back into view before the heights are
    // re-equalised, otherwise the reset shifts the view down by a line.
    const scrollIntoView = /** @type {any} */ (
      Element.prototype.scrollIntoView
    );
    expect(scrollIntoView).toHaveBeenCalled();
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(
      document.getElementById("modal-line-0")?.closest(".lyric-row"),
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

describe("LRCEditor line selection", () => {
  /**
   * @param {number} index
   */
  function row(index) {
    return /** @type {HTMLElement} */ (
      document.querySelectorAll(".lyric-row")[index]
    );
  }

  /**
   * @param {number} index
   */
  function isSelected(index) {
    return row(index).className.includes("selected");
  }

  /**
   * Click a line's lyric text, which is what selects a line.
   * @param {number} index
   * @param {{ shiftKey?: boolean, ctrlKey?: boolean }} [modifiers]
   */
  async function clickLine(index, modifiers = {}) {
    const cell = document.getElementById(`modal-line-${index}`);
    const target = /** @type {HTMLElement} */ (
      cell?.querySelector("[role=button]")
    );
    await fireEvent(
      /** @type {HTMLElement} */ (target ?? cell),
      new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        ...modifiers,
      }),
    );
  }

  /**
   * Start editing a line with a double click, as a pointer would.
   * @param {number} index
   */
  async function editLine(index) {
    await clickLine(index);
    await fireEvent.dblClick(
      /** @type {HTMLElement} */ (
        document
          .getElementById(`modal-line-${index}`)
          ?.querySelector("button, [role=button]")
      ),
    );
  }

  const threeLines = {
    isOpen: true,
    initialLyrics: "one\ntwo\nthree",
    initialTimestamps: ["[00:10.00]", "[00:20.00]", "[00:30.00]"],
  };

  beforeEach(() => {
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
    delete (/** @type {any} */ (Element.prototype).scrollIntoView);
    vi.unstubAllGlobals();
    toast.clear();
  });

  it("selects one line at a time", async () => {
    render(LRCEditor, { props: threeLines });

    await clickLine(0);
    expect(isSelected(0)).toBe(true);
    expect(isSelected(1)).toBe(false);

    await clickLine(1);
    expect(isSelected(0)).toBe(false);
    expect(isSelected(1)).toBe(true);
  });

  it("keeps the active line and the selection apart", async () => {
    render(LRCEditor, { props: threeLines });

    window.dispatchEvent(
      new CustomEvent("player-time-update", { detail: { time: 21 } }),
    );
    await tick();
    await clickLine(2);

    // Playback highlights line 1; the user selected line 2.
    expect(row(1).className).toContain("playing");
    expect(isSelected(1)).toBe(false);
    expect(isSelected(2)).toBe(true);
    expect(row(2).className).not.toContain("playing");
  });

  it("extends the selection with Shift+click", async () => {
    render(LRCEditor, { props: threeLines });

    await clickLine(0);
    await clickLine(2, { shiftKey: true });

    expect(isSelected(0)).toBe(true);
    expect(isSelected(1)).toBe(true);
    expect(isSelected(2)).toBe(true);
    expect(screen.getByRole("button", { name: "Selected (3)" })).toBeTruthy();
  });

  it("selects from the lyrics, not from the timestamps", async () => {
    render(LRCEditor, { props: threeLines });

    await clickLine(1);
    await fireEvent.click(
      /** @type {HTMLElement} */ (document.getElementById("modal-timestamp-0")),
    );

    // The timestamp seeks; it does not add the line to the selection.
    expect(isSelected(0)).toBe(false);
    expect(isSelected(1)).toBe(true);
  });

  it("toggles one line with Ctrl/Cmd+click", async () => {
    render(LRCEditor, { props: threeLines });

    await clickLine(1);
    await clickLine(2, { ctrlKey: true });
    expect(isSelected(1)).toBe(true);
    expect(isSelected(2)).toBe(true);

    await clickLine(1, { ctrlKey: true });
    expect(isSelected(1)).toBe(false);
    expect(isSelected(2)).toBe(true);
  });

  it("edits a line in place and commits with Enter", async () => {
    const onSave = vi.fn();
    render(LRCEditor, { props: { ...threeLines, onSave } });

    await editLine(1);
    const input = /** @type {HTMLInputElement} */ (
      screen.getByLabelText("Line 2 text")
    );
    expect(input.value).toBe("two");

    await fireEvent.input(input, { target: { value: "changed" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await tick();

    expect(screen.queryByLabelText("Line 2 text")).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Save to File" }));
    expect(onSave).toHaveBeenCalledWith({
      lyrics: "one\nchanged\nthree",
      timestamps: ["[00:10.00]", "[00:20.00]", "[00:30.00]"],
      synchronizedLyrics:
        "[00:10.00] one\n[00:20.00] changed\n[00:30.00] three",
      hasTimestamps: true,
    });
  });

  it("cancels an in-place edit with Escape without closing the editor", async () => {
    const onClose = vi.fn();
    render(LRCEditor, { props: { ...threeLines, onClose } });

    await editLine(1);
    const input = /** @type {HTMLInputElement} */ (
      screen.getByLabelText("Line 2 text")
    );
    await fireEvent.input(input, { target: { value: "dropped" } });
    await fireEvent.keyDown(input, { key: "Escape" });
    await tick();

    expect(screen.queryByLabelText("Line 2 text")).toBeNull();
    expect(screen.getAllByText("two").length).toBeGreaterThan(0);
    expect(screen.queryByText("dropped")).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shifts only the selected lines from the footer", async () => {
    render(LRCEditor, { props: threeLines });

    await clickLine(1);
    await clickLine(2, { shiftKey: true });
    await fireEvent.click(screen.getByRole("button", { name: "Selected (2)" }));
    await fireEvent.input(screen.getByLabelText("Shift amount in seconds"), {
      target: { value: "1.5" },
    });
    await fireEvent.click(screen.getByLabelText("Shift all timestamps later"));

    expect(screen.getAllByText("[00:10.00]").length).toBeGreaterThan(0);
    expect(screen.getAllByText("[00:21.50]").length).toBeGreaterThan(0);
    expect(screen.getAllByText("[00:31.50]").length).toBeGreaterThan(0);
    expect(get(toast).at(-1)?.message).toBe("Shifted 2 timestamps by +1.50s");
  });

  it("keeps the selection after a shift so it can be repeated", async () => {
    render(LRCEditor, { props: threeLines });

    await clickLine(1);
    await clickLine(2, { shiftKey: true });
    await fireEvent.click(screen.getByRole("button", { name: "Selected (2)" }));
    await fireEvent.input(screen.getByLabelText("Shift amount in seconds"), {
      target: { value: "1" },
    });
    await fireEvent.click(screen.getByLabelText("Shift all timestamps later"));

    expect(isSelected(1)).toBe(true);
    expect(isSelected(2)).toBe(true);

    await fireEvent.click(screen.getByLabelText("Shift all timestamps later"));
    expect(screen.getAllByText("[00:22.00]").length).toBeGreaterThan(0);
    expect(get(toast).at(-1)?.message).toBe("Shifted 2 timestamps by +1.00s");
  });

  it("does not select from the timestamp column", async () => {
    render(LRCEditor, { props: threeLines });

    await fireEvent.click(
      /** @type {HTMLElement} */ (document.getElementById("modal-timestamp-1")),
    );
    for (let i = 0; i < 3; i++) expect(isSelected(i)).toBe(false);

    // A placeholder row has no jump target, but it is not part of the
    // selection either, so clicking it does nothing at all.
    await fireEvent.click(
      /** @type {HTMLElement} */ (document.getElementById("modal-timestamp-0")),
    );
    for (let i = 0; i < 3; i++) expect(isSelected(i)).toBe(false);
  });

  it("marks the playing line in the timestamp column", async () => {
    render(LRCEditor, { props: threeLines });

    window.dispatchEvent(
      new CustomEvent("player-time-update", { detail: { time: 21 } }),
    );
    await tick();

    const cell = /** @type {HTMLElement} */ (
      document.querySelectorAll(".timestamp-cell")[1]
    );
    expect(row(1).className).toContain("playing");
    expect(cell.textContent).toContain("[00:20.00]");
  });

  it("only offers the selection scope once something is selected", async () => {
    render(LRCEditor, { props: threeLines });

    expect(
      /** @type {HTMLButtonElement} */ (
        screen.getByRole("button", { name: "Selected" })
      ).disabled,
    ).toBe(true);

    await clickLine(0);
    const selected = /** @type {HTMLButtonElement} */ (
      screen.getByRole("button", { name: "Selected (1)" })
    );
    expect(selected.disabled).toBe(false);

    await fireEvent.click(selected);
    expect(selected.getAttribute("aria-pressed")).toBe("true");
    expect(
      screen.getByLabelText("Shift all timestamps later").getAttribute("title"),
    ).toBe("Shift timestamps later on 1 selected line");
  });

  it("shifts one line from its own row buttons", async () => {
    render(LRCEditor, { props: threeLines });

    await fireEvent.input(screen.getByLabelText("Shift amount in seconds"), {
      target: { value: "0.5" },
    });
    await fireEvent.click(screen.getByLabelText("Shift line 2 later"));

    expect(screen.getAllByText("[00:20.50]").length).toBeGreaterThan(0);
    expect(screen.getAllByText("[00:10.00]").length).toBeGreaterThan(0);
    expect(get(toast).at(-1)?.message).toBe(
      "Shifted 1 timestamp by +0.50s on this line",
    );
  });

  it("refuses a per-line shift that would cross its neighbour", async () => {
    render(LRCEditor, {
      props: {
        isOpen: true,
        initialLyrics: "one\ntwo",
        initialTimestamps: ["[00:10.00]", "[00:15.00]"],
      },
    });

    await fireEvent.input(screen.getByLabelText("Shift amount in seconds"), {
      target: { value: "6" },
    });
    await fireEvent.click(screen.getByLabelText("Shift line 1 later"));

    expect(get(toast).at(-1)?.message).toBe(
      "Line 1 would move after [00:15.00] on the line below",
    );
    expect(screen.getAllByText("[00:10.00]").length).toBeGreaterThan(0);
  });

  it("adds a line below the selection and starts editing it", async () => {
    const onSave = vi.fn();
    render(LRCEditor, { props: { ...threeLines, onSave } });

    await clickLine(0);
    await fireEvent.click(screen.getByRole("button", { name: "+ Line" }));
    await tick();

    const input = /** @type {HTMLInputElement} */ (
      screen.getByLabelText("Line 2 text")
    );
    expect(input.value).toBe("");
    await fireEvent.input(input, { target: { value: "inserted" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await tick();

    await fireEvent.click(screen.getByRole("button", { name: "Save to File" }));
    expect(onSave).toHaveBeenCalledWith({
      lyrics: "one\ninserted\ntwo\nthree",
      timestamps: ["[00:10.00]", "[--:--.--]", "[00:20.00]", "[00:30.00]"],
      synchronizedLyrics:
        "[00:10.00] one\ninserted\n[00:20.00] two\n[00:30.00] three",
      hasTimestamps: true,
    });
  });

  it("deletes the selected lines with their timestamps", async () => {
    const onSave = vi.fn();
    render(LRCEditor, { props: { ...threeLines, onSave } });

    await clickLine(1);
    await fireEvent.click(screen.getByRole("button", { name: "Delete (1)" }));
    await tick();

    expect(screen.queryByText("two")).toBeNull();
    expect(get(toast).at(-1)?.message).toBe("Deleted 1 line");

    await fireEvent.click(screen.getByRole("button", { name: "Save to File" }));
    expect(onSave).toHaveBeenCalledWith({
      lyrics: "one\nthree",
      timestamps: ["[00:10.00]", "[00:30.00]"],
      synchronizedLyrics: "[00:10.00] one\n[00:30.00] three",
      hasTimestamps: true,
    });
  });

  it("disables the add and delete buttons without a selection", () => {
    render(LRCEditor, { props: threeLines });

    expect(
      /** @type {HTMLButtonElement} */ (
        screen.getByRole("button", { name: "+ Line" })
      ).disabled,
    ).toBe(true);
    expect(
      /** @type {HTMLButtonElement} */ (
        screen.getByRole("button", { name: "Delete" })
      ).disabled,
    ).toBe(true);
  });
});
