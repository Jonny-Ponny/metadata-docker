import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";

import MetadataEditor from "../MetadataEditor.svelte";

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
     * @param {{ method?: string }} [options]
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
    expect(screen.getByLabelText("composer")).toBe(composer);
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
