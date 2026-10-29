import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/svelte";
import { tick } from "svelte";

import MetadataEditor from "../MetadataEditor.svelte";
import { toast } from "../../stores/toast.store.js";

const filePath = "folder/song.mp3";

/**
 * @param {number} status
 * @param {Record<string, unknown>} body
 */
function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  };
}

/**
 * @param {Record<string, unknown>} [metadata]
 */
function stubMetadata(metadata = {}) {
  const fetchMock = vi.fn(
    /**
     * @param {string} url
     * @param {RequestInit} [options]
     */
    (url, options = {}) => {
      if (options.method === "POST") {
        return Promise.resolve(jsonResponse(200, { success: true }));
      }
      return Promise.resolve(
        jsonResponse(200, {
          title: "Song",
          album: "Album",
          artist: "Artist",
          albumArtist: "Album Artist",
          trackNumber: 3,
          diskNumber: 1,
          date: "2024",
          genre: "Rock",
          composer: "Composer",
          ...metadata,
        }),
      );
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * @param {HTMLElement} element
 * @param {string} value
 */
async function typeInto(element, value) {
  await fireEvent.input(element, { target: { value } });
  await tick();
}

describe("MetadataEditor", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
    toast.clear();
    document
      .querySelectorAll('input[type="file"]')
      .forEach((input) => input.remove());
  });

  it("loads the file metadata and shows the filename", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });

    expect(screen.getByText("song.mp3")).toBeTruthy();
    expect(await screen.findByDisplayValue("Song")).toBeTruthy();
    expect(screen.getByDisplayValue("Album Artist")).toBeTruthy();
    expect(screen.getByDisplayValue("3")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/metadata?path=${encodeURIComponent(filePath)}`,
    );
  });

  it("shows the read-only banner for an unsupported file", async () => {
    stubMetadata({ readOnly: true, supported: false, format: "wav" });

    render(MetadataEditor, { props: { filePath: "folder/song.wav" } });

    const note = await screen.findByRole("note");
    expect(note.textContent).toContain("Read-only");
    expect(note.textContent).toContain(
      "wav files are not supported for tag editing.",
    );
    expect(screen.queryByText("Apply All Changes")).toBeTruthy();
    expect(
      /** @type {HTMLInputElement} */ (screen.getByLabelText("Title")).readOnly,
    ).toBe(true);
  });

  it("marks an edited field dirty and saves it to the file", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    const title = screen.getByLabelText("Title");
    await typeInto(title, "New title");

    expect(title.closest(".field")?.classList.contains("dirty")).toBe(true);

    await fireEvent.click(
      screen.getByRole("button", { name: "Apply All Changes" }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/file",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            path: filePath,
            field: "title",
            value: "New title",
          }),
        }),
      ),
    );
  });

  it("saves a field on Enter without leaving the input", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    const title = screen.getByLabelText("Title");
    await typeInto(title, "Entered");
    await fireEvent.keyDown(title, { key: "Enter" });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/file",
        expect.objectContaining({
          body: JSON.stringify({
            path: filePath,
            field: "title",
            value: "Entered",
          }),
        }),
      ),
    );
  });

  it("expands the other-fields section", async () => {
    stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    const other = screen.getByRole("button", { name: "▶ Other" });
    expect(screen.queryByDisplayValue("Composer")).toBeNull();

    await fireEvent.click(other);

    const composer = await screen.findByDisplayValue("Composer");
    expect(composer.closest(".field")).toBeTruthy();
    expect(screen.getByLabelText("Composer")).toBe(composer);
  });

  it("shows field descriptions as hover tooltips", async () => {
    stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    expect(screen.getByText("Title").getAttribute("title")).toContain(
      "Song title",
    );

    await fireEvent.click(screen.getByText("▶ Other"));

    expect(screen.getByText("Comment").getAttribute("title")).toContain(
      "Free-form notes",
    );
    expect(screen.getByText("Composer").getAttribute("title")).toContain(
      "writer",
    );
  });

  it("reloads the metadata when a refresh event names the file", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    const initialCalls = fetchMock.mock.calls.length;

    window.dispatchEvent(
      new CustomEvent("refreshMetadata", { detail: { path: filePath } }),
    );

    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls),
    );
  });

  it("does not fetch when there is no file selected", () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath: "" } });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("Apply All Changes")).toBeTruthy();
  });
});

describe("MetadataEditor editing actions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
    toast.clear();
    document
      .querySelectorAll('input[type="file"]')
      .forEach((input) => input.remove());
  });

  /**
   * Hold a hold-to-confirm control for its whole duration.
   * @param {HTMLElement} button
   * @param {number} [duration]
   */
  async function hold(button, duration = 800) {
    vi.useFakeTimers();
    try {
      await fireEvent.mouseDown(button);
      await vi.advanceTimersByTimeAsync(duration);
    } finally {
      vi.useRealTimers();
    }
  }

  /**
   * @param {string} label
   */
  async function focusField(label) {
    await fireEvent.focus(screen.getByLabelText(label));
    await tick();
  }

  it("hides every editing control for a read-only file", async () => {
    stubMetadata({ readOnly: true, supported: false, format: "wav" });

    render(MetadataEditor, { props: { filePath: "folder/song.wav" } });
    await screen.findByRole("note");

    expect(screen.queryByText("Recursive")).toBeNull();
    expect(screen.queryByText("Edit synced lyrics")).toBeNull();
    expect(screen.queryByText("Edit unsynced lyrics")).toBeNull();
    expect(screen.queryByText("+ Add new field")).toBeNull();
    expect(screen.queryByText("Apply All Changes")).toBeTruthy();
  });

  it("reports a failed metadata load", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(500, {}))),
    );

    render(MetadataEditor, { props: { filePath } });

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith(
        "Failed to load metadata: Failed to fetch metadata: Error",
      ),
    );
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("applies an edited field to the current folder", async () => {
    const fetchMock = stubMetadata();
    const successSpy = vi.spyOn(toast, "success");

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await focusField("Title");

    await hold(
      screen.getByTitle(
        "Hold to apply to all files in folder (same level only)",
      ),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/folder/current",
        expect.objectContaining({
          body: JSON.stringify({
            path: "folder",
            field: "title",
            value: "Song",
          }),
        }),
      ),
    );
    expect(successSpy).toHaveBeenCalledWith("Updated folder: title");
  });

  it("applies a field recursively when the recursive option is on", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByLabelText("Recursive"));
    await focusField("Title");

    await hold(
      screen.getByTitle(
        "Hold to apply to all files in folder (including subfolders)",
      ),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/folder",
        expect.objectContaining({
          body: JSON.stringify({
            path: "folder",
            field: "title",
            value: "Song",
          }),
        }),
      ),
    );
  });

  it("uses the library root when a file sits at the top level", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath: "song.mp3" } });
    await screen.findByDisplayValue("Song");
    await focusField("Title");

    await hold(
      screen.getByTitle(
        "Hold to apply to all files in folder (same level only)",
      ),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/folder/current",
        expect.objectContaining({
          body: JSON.stringify({ path: "/", field: "title", value: "Song" }),
        }),
      ),
    );
  });

  it("reports a failed folder apply", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    stubMetadata();
    const fetchMock = /** @type {import("vitest").Mock} */ (globalThis.fetch);
    const defaultImpl = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(
      /** @param {string} url @param {RequestInit} [options] */
      (url, options = {}) =>
        options.method === "POST"
          ? Promise.resolve(jsonResponse(500, { error: "no space" }))
          : defaultImpl?.(url, options),
    );

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await focusField("Title");

    await hold(
      screen.getByTitle(
        "Hold to apply to all files in folder (same level only)",
      ),
    );

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith(
        "Failed to update folder: no space",
      ),
    );
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("deletes a field from the current file after a hold", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await focusField("Title");

    await hold(
      screen.getByTitle("Hold to delete this field from current file"),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/field/delete",
        expect.objectContaining({
          body: JSON.stringify({ path: filePath, field: "title" }),
        }),
      ),
    );
  });

  it("deletes a field from every file in the folder when configured", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByLabelText("Recursive"));
    await fireEvent.click(
      screen.getByLabelText("Tag deletion applies to folder"),
    );
    await focusField("Title");

    await hold(
      screen.getByTitle("Hold to delete this field from all files in folder"),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/field/delete",
        expect.objectContaining({
          body: JSON.stringify({
            path: "folder",
            field: "title",
            recursive: true,
          }),
        }),
      ),
    );
  });

  it("reports a failed field delete", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    stubMetadata();
    const fetchMock = /** @type {import("vitest").Mock} */ (globalThis.fetch);
    const defaultImpl = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(
      /** @param {string} url @param {RequestInit} [options] */
      (url, options = {}) =>
        options.method === "POST"
          ? Promise.resolve(jsonResponse(500, { error: "locked" }))
          : defaultImpl?.(url, options),
    );

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await focusField("Title");

    await hold(
      screen.getByTitle("Hold to delete this field from current file"),
    );

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith("Failed to delete: locked"),
    );
  });

  it("reports a failed field save", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const errorSpy = vi.spyOn(toast, "error");
    stubMetadata();
    const fetchMock = /** @type {import("vitest").Mock} */ (globalThis.fetch);
    const defaultImpl = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(
      /** @param {string} url @param {RequestInit} [options] */
      (url, options = {}) =>
        options.method === "POST"
          ? Promise.resolve(jsonResponse(500, { error: "read only" }))
          : defaultImpl?.(url, options),
    );

    render(MetadataEditor, { props: { filePath } });
    const title = await screen.findByDisplayValue("Song");
    await typeInto(title, "Changed");
    await fireEvent.keyDown(title, { key: "Enter" });

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith("Failed to update: read only"),
    );
  });

  it("uploads a cover for the current file", async () => {
    const fetchMock = stubMetadata();
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(
      screen.getByTitle("Upload cover art for this file only"),
    );

    const input = /** @type {HTMLInputElement} */ (
      document.querySelector('input[type="file"]')
    );
    const file = new File(["image"], "cover.jpg", { type: "image/jpeg" });
    Object.defineProperty(input, "files", {
      value: [file],
      configurable: true,
    });
    await fireEvent.change(input);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/picture/file",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = fetchMock.mock.calls.find(
      ([url]) => url === "/api/metadata/picture/file",
    );
    const form = /** @type {FormData} */ (
      /** @type {unknown} */ (call?.[1]?.body)
    );
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("path")).toBe(filePath);
    expect(form.get("file")).toBe(file);
  });

  it("uploads a cover to the folder after a hold", async () => {
    const fetchMock = stubMetadata();
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );

    await hold(
      screen.getByTitle(
        "Hold to apply to all files in folder (same level only)",
      ),
    );
    const input = /** @type {HTMLInputElement} */ (
      document.querySelector('input[type="file"]')
    );
    const file = new File(["image"], "cover.jpg", { type: "image/jpeg" });
    Object.defineProperty(input, "files", {
      value: [file],
      configurable: true,
    });
    await fireEvent.change(input);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/picture/folder/current",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = fetchMock.mock.calls.find(
      ([url]) => url === "/api/metadata/picture/folder/current",
    );
    const form = /** @type {FormData} */ (
      /** @type {unknown} */ (call?.[1]?.body)
    );
    expect(form.get("path")).toBe("folder");
  });

  it("rejects a cover that is not an image", async () => {
    const errorSpy = vi.spyOn(toast, "error");
    stubMetadata();
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(
      screen.getByTitle("Upload cover art for this file only"),
    );

    const input = /** @type {HTMLInputElement} */ (
      document.querySelector('input[type="file"]')
    );
    const file = new File(["text"], "notes.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", {
      value: [file],
      configurable: true,
    });
    await fireEvent.change(input);

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith("Please select an image file"),
    );
  });

  it("rejects a cover over five megabytes", async () => {
    const errorSpy = vi.spyOn(toast, "error");
    stubMetadata();
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(
      screen.getByTitle("Upload cover art for this file only"),
    );

    const input = /** @type {HTMLInputElement} */ (
      document.querySelector('input[type="file"]')
    );
    Object.defineProperty(input, "files", {
      value: [
        {
          type: "image/jpeg",
          size: 5 * 1024 * 1024 + 1,
        },
      ],
      configurable: true,
    });
    await fireEvent.change(input);

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith("Image must be less than 5MB"),
    );
  });

  it("applies a cover URL to the current file", async () => {
    const fetchMock = stubMetadata();
    const successSpy = vi.spyOn(toast, "success");
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(screen.getByTitle("Set cover art from URL"));
    await typeInto(
      screen.getByLabelText("Cover art image URL"),
      "https://example.com/cover.jpg",
    );
    await fireEvent.click(
      screen.getByTitle("Apply this URL to the current file"),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/picture/url",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            path: filePath,
            url: "https://example.com/cover.jpg",
          }),
        }),
      ),
    );
    expect(successSpy).toHaveBeenCalledWith("Updated cover art from URL");
    expect(screen.queryByLabelText("Cover art image URL")).toBeNull();
  });

  it("applies a cover URL to the whole folder", async () => {
    const fetchMock = stubMetadata();
    const refreshHandler = vi.fn();
    window.addEventListener("refreshFileTree", refreshHandler);
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(screen.getByTitle("Set cover art from URL"));
    await typeInto(
      screen.getByLabelText("Cover art image URL"),
      "https://example.com/cover.jpg",
    );
    await hold(
      screen.getByTitle(
        "Hold to apply this URL to all files in folder (same level only)",
      ),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/picture/url/folder/current",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            path: "folder",
            url: "https://example.com/cover.jpg",
          }),
        }),
      ),
    );
    await waitFor(() => expect(refreshHandler).toHaveBeenCalledTimes(1));
    window.removeEventListener("refreshFileTree", refreshHandler);
  });

  it("disables applying a URL that is not http(s)", async () => {
    stubMetadata();
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(screen.getByTitle("Set cover art from URL"));
    await typeInto(screen.getByLabelText("Cover art image URL"), "cover.jpg");

    expect(
      /** @type {HTMLButtonElement} */ (
        screen.getByTitle("Apply this URL to the current file")
      ).disabled,
    ).toBe(true);
  });

  it("deletes the cover art after a hold", async () => {
    const fetchMock = stubMetadata({ picture: "data:image/jpeg;base64,AAAA" });
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await hold(screen.getByTitle("Hold to delete cover art"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/picture/delete",
        expect.objectContaining({
          body: JSON.stringify({ path: filePath }),
        }),
      ),
    );
  });

  it("saves the cover next to the track and refreshes the tree", async () => {
    const fetchMock = stubMetadata({ picture: "data:image/jpeg;base64,AAAA" });
    const refreshHandler = vi.fn();
    window.addEventListener("refreshFileTree", refreshHandler);
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(screen.getByTitle("Save as cover.*"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/picture/save-as-file",
        expect.objectContaining({
          body: JSON.stringify({ path: filePath }),
        }),
      ),
    );
    await waitFor(() => expect(refreshHandler).toHaveBeenCalledTimes(1));
    window.removeEventListener("refreshFileTree", refreshHandler);
  });

  it("opens the full-size cover and closes it", async () => {
    stubMetadata({ picture: "data:image/jpeg;base64,AAAA" });
    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    await fireEvent.mouseEnter(
      /** @type {Element} */ (container.querySelector(".cover-art-overlay")),
    );
    await fireEvent.click(screen.getByTitle("View full size"));

    expect(screen.getByAltText("Full size cover art")).toBeTruthy();
    const modal = /** @type {HTMLElement} */ (
      container.querySelector(".full-image-modal")
    );
    await fireEvent.click(within(modal).getByRole("button", { name: "Close" }));

    expect(screen.queryByAltText("Full size cover art")).toBeNull();
  });

  it("saves unsynced lyrics from the modal", async () => {
    const fetchMock = stubMetadata({ unsyncedLyrics: "Old words" });

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByText("Edit unsynced lyrics"));

    const textarea = screen.getByPlaceholderText(
      "Enter unsynced lyrics here...",
    );
    expect(/** @type {HTMLTextAreaElement} */ (textarea).value).toBe(
      "Old words",
    );
    await fireEvent.input(textarea, { target: { value: "New words" } });
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/file",
        expect.objectContaining({
          body: JSON.stringify({
            path: filePath,
            field: "unsyncedLyrics",
            value: "New words",
          }),
        }),
      ),
    );
    await waitFor(() =>
      expect(
        screen.queryByPlaceholderText("Enter unsynced lyrics here..."),
      ).toBeNull(),
    );
  });

  it("closes the unsynced lyrics modal without saving", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByText("Edit unsynced lyrics"));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByPlaceholderText("Enter unsynced lyrics here..."),
    ).toBeNull();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/metadata/file",
      expect.anything(),
    );
  });

  it("does nothing when Apply All finds no values", async () => {
    const infoSpy = vi.spyOn(toast, "info");
    const fetchMock = stubMetadata({
      title: "",
      album: "",
      artist: "",
      albumArtist: "",
      trackNumber: "",
      diskNumber: "",
      date: "",
      genre: "",
      comment: "",
      description: "",
      composer: "",
    });

    render(MetadataEditor, { props: { filePath } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await fireEvent.click(screen.getByText("Apply All Changes"));

    await waitFor(() =>
      expect(infoSpy).toHaveBeenCalledWith("No changes to apply"),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/metadata/file",
      expect.anything(),
    );
  });

  it("adds a custom field and saves it to the file", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByText("+ Add new field"));

    const nameInput = screen.getByPlaceholderText("Field name");
    const valueInput = screen.getByPlaceholderText("Value");
    await fireEvent.input(nameInput, { target: { value: "mood" } });
    await fireEvent.input(valueInput, { target: { value: "Happy" } });
    await fireEvent.focusIn(valueInput);
    await tick();

    await fireEvent.click(screen.getByTitle("Apply to this file only"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/file",
        expect.objectContaining({
          body: JSON.stringify({
            path: filePath,
            field: "mood",
            value: "Happy",
          }),
        }),
      ),
    );
  });

  it("applies a custom field with Apply All", async () => {
    const fetchMock = stubMetadata({
      title: "",
      album: "",
      artist: "",
      albumArtist: "",
      trackNumber: "",
      diskNumber: "",
      date: "",
      genre: "",
      composer: "",
    });

    render(MetadataEditor, { props: { filePath } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await fireEvent.click(screen.getByText("+ Add new field"));
    await fireEvent.input(screen.getByPlaceholderText("Field name"), {
      target: { value: "mood" },
    });
    await fireEvent.input(screen.getByPlaceholderText("Value"), {
      target: { value: "Calm" },
    });
    await fireEvent.click(screen.getByText("Apply All Changes"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/metadata/file",
        expect.objectContaining({
          body: JSON.stringify({
            path: filePath,
            field: "mood",
            value: "Calm",
          }),
        }),
      ),
    );
  });

  it("sorts the other fields alphabetically by name", async () => {
    stubMetadata({
      publisher: "Label",
      customFields: [
        { name: "zeta", value: "Z" },
        { name: "Alpha", value: "A" },
      ],
    });

    const { container } = render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByText("▶ Other"));

    const ids = [...container.querySelectorAll(".other-fields input")].map(
      (input) => input.id,
    );
    expect(ids).toEqual(["Alpha", "composer", "publisher", "zeta"]);
  });

  it("tracks and clears dirty state for an other field", async () => {
    stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");
    await fireEvent.click(screen.getByText("▶ Other"));

    const composer = screen.getByLabelText("Composer");
    await typeInto(composer, "Someone else");

    expect(
      /** @type {HTMLElement} */ (
        composer.closest(".field")
      ).classList.contains("dirty"),
    ).toBe(true);

    await typeInto(composer, "Composer");

    expect(
      /** @type {HTMLElement} */ (
        composer.closest(".field")
      ).classList.contains("dirty"),
    ).toBe(false);
  });

  it("refreshes when the file or its folder changes", async () => {
    const fetchMock = stubMetadata();

    render(MetadataEditor, { props: { filePath } });
    await screen.findByDisplayValue("Song");

    const initial = fetchMock.mock.calls.length;
    window.dispatchEvent(
      new CustomEvent("refreshMetadata", { detail: { path: "folder" } }),
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initial),
    );

    const afterFolder = fetchMock.mock.calls.length;
    window.dispatchEvent(
      new CustomEvent("refreshMetadata", { detail: { path: "elsewhere" } }),
    );
    await tick();
    expect(fetchMock.mock.calls.length).toBe(afterFolder);

    window.dispatchEvent(new CustomEvent("refreshMetadata", { detail: {} }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThan(afterFolder),
    );
  });
});
