import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";

const { toastMock } = vi.hoisted(() => ({
  toastMock: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("../../stores/toast.store.js", () => ({ toast: toastMock }));

import BulkEditor from "../BulkEditor.svelte";

const folder = {
  name: "album",
  path: "album",
  type: "directory",
  children: [
    { name: "01.mp3", path: "album/01.mp3", type: "file", file_type: "audio" },
    { name: "02.mp3", path: "album/02.mp3", type: "file", file_type: "audio" },
    { name: "03.mp3", path: "album/03.mp3", type: "file", file_type: "audio" },
    {
      name: "cd2",
      path: "album/cd2",
      type: "directory",
      children: [
        {
          name: "04.mp3",
          path: "album/cd2/04.mp3",
          type: "file",
          file_type: "audio",
        },
      ],
    },
  ],
};

/** @type {Record<string, Record<string, string>>} */
const baseMetadata = {
  "album/01.mp3": { artist: "Same", album: "One" },
  "album/02.mp3": { artist: "Same", album: "Two" },
  "album/03.mp3": { artist: "Same", album: "Three" },
  "album/cd2/04.mp3": { artist: "Other", album: "Four" },
};

/**
 * @param {{ batch?: () => Promise<any>, metadata?: Record<string, Record<string, string>> }} [options]
 */
function stubFetch(options = {}) {
  const metadata = options.metadata ?? baseMetadata;
  const fetchMock = vi.fn(
    /**
     * @param {string} url
     * @param {RequestInit} [_init]
     */
    (url, _init) => {
      if (url === "/api/metadata/batch") {
        return options.batch
          ? options.batch()
          : Promise.resolve({
              ok: true,
              status: 200,
              json: async () => ({
                success: true,
                message: "Updated 3 of 3 files",
                failed_files: [],
              }),
            });
      }
      const path =
        new URL(url, "http://localhost").searchParams.get("path") ?? "";
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => metadata[path] ?? {},
      });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * @param {ReturnType<typeof stubFetch>} fetchMock
 */
function batchCalls(fetchMock) {
  return fetchMock.mock.calls.filter(([url]) => url === "/api/metadata/batch");
}

/**
 * @param {HTMLElement} element
 * @returns {HTMLInputElement & HTMLButtonElement}
 */
function field(element) {
  return /** @type {HTMLInputElement & HTMLButtonElement} */ (element);
}

async function renderLoaded() {
  render(BulkEditor, { props: { folderNode: folder } });
  await waitFor(() => expect(screen.queryByText("Loading tags…")).toBeNull());
}

describe("BulkEditor", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("selects every direct audio file by default", async () => {
    stubFetch();
    await renderLoaded();

    expect(screen.getByText("3 of 3 files selected")).toBeTruthy();
    expect(screen.queryByText("cd2/04.mp3")).toBeNull();
  });

  it("shows shared values and marks differing ones", async () => {
    stubFetch();
    await renderLoaded();

    expect(field(screen.getByLabelText("Artist")).value).toBe("Same");
    const album = screen.getByLabelText("Album");
    expect(field(album).value).toBe("");
    expect(field(album).placeholder).toBe("(multiple values)");
  });

  it("includes subfolders when asked", async () => {
    stubFetch();
    await renderLoaded();

    await fireEvent.click(screen.getByLabelText("Include subfolders"));
    await waitFor(() =>
      expect(screen.getByText("4 of 4 files selected")).toBeTruthy(),
    );
    await waitFor(() =>
      expect(field(screen.getByLabelText("Artist")).placeholder).toBe(
        "(multiple values)",
      ),
    );
  });

  it("selects a range with shift+click", async () => {
    stubFetch();
    await renderLoaded();

    await fireEvent.click(screen.getByLabelText("Select all"));
    expect(screen.getByText("0 of 3 files selected")).toBeTruthy();

    await fireEvent.click(screen.getByLabelText("01.mp3"));
    await fireEvent.click(screen.getByLabelText("03.mp3"), { shiftKey: true });

    expect(screen.getByText("3 of 3 files selected")).toBeTruthy();
  });

  it("sends only touched fields after confirmation", async () => {
    const fetchMock = stubFetch();
    await renderLoaded();

    await fireEvent.input(screen.getByLabelText("Album"), {
      target: { value: "Bulk Album" },
    });
    await fireEvent.input(screen.getByLabelText("Disk Number"), {
      target: { value: "1/2" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "Remove Genre from all" }),
    );
    await fireEvent.click(
      screen.getByRole("button", { name: "Apply to 3 file(s)" }),
    );

    expect(batchCalls(fetchMock)).toHaveLength(0);
    const confirm = screen.getByRole("region", {
      name: "Confirm bulk changes",
    });
    expect(confirm.textContent).toContain("Album: “Bulk Album”");
    expect(confirm.textContent).toContain("Genre: remove");

    await fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(batchCalls(fetchMock)).toHaveLength(1));
    const [, init] = batchCalls(fetchMock)[0];
    expect(JSON.parse(/** @type {string} */ (init?.body))).toEqual({
      paths: ["album/01.mp3", "album/02.mp3", "album/03.mp3"],
      set: { album: "Bulk Album", diskNumber: "1/2" },
      delete: ["genre"],
    });
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith("Updated 3 of 3 files"),
    );
  });

  it("does not send a field typed back to its shared value", async () => {
    stubFetch();
    await renderLoaded();

    const artist = screen.getByLabelText("Artist");
    await fireEvent.input(artist, { target: { value: "Changed" } });
    expect(
      field(screen.getByRole("button", { name: "Apply to 3 file(s)" }))
        .disabled,
    ).toBe(false);

    await fireEvent.input(artist, { target: { value: "Same" } });
    expect(
      field(screen.getByRole("button", { name: "Apply to 3 file(s)" }))
        .disabled,
    ).toBe(true);
  });

  it("blocks an invalid disk number", async () => {
    stubFetch();
    await renderLoaded();

    await fireEvent.input(screen.getByLabelText("Disk Number"), {
      target: { value: "one" },
    });
    await tick();

    expect(screen.getByRole("alert").textContent).toContain("1/2");
    expect(
      field(screen.getByRole("button", { name: "Apply to 3 file(s)" }))
        .disabled,
    ).toBe(true);
  });

  it("can undo a pending removal", async () => {
    stubFetch();
    await renderLoaded();

    await fireEvent.click(
      screen.getByRole("button", { name: "Remove Artist from all" }),
    );
    expect(field(screen.getByLabelText("Artist")).disabled).toBe(true);

    await fireEvent.click(
      screen.getByRole("button", { name: "Undo Artist change" }),
    );
    expect(field(screen.getByLabelText("Artist")).value).toBe("Same");
    expect(
      field(screen.getByRole("button", { name: "Apply to 3 file(s)" }))
        .disabled,
    ).toBe(true);
  });

  it("reports files the server could not update", async () => {
    stubFetch({
      batch: () =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            message: "Updated 2 of 3 files",
            failed_files: ["album/02.mp3"],
          }),
        }),
    });
    await renderLoaded();

    await fireEvent.input(screen.getByLabelText("Artist"), {
      target: { value: "New" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "Apply to 3 file(s)" }),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(toastMock.warning).toHaveBeenCalledWith(
        "Updated 2 of 3 files. Failed: album/02.mp3",
        8000,
      ),
    );
  });

  it("shows the server error and keeps the edits", async () => {
    stubFetch({
      batch: () =>
        Promise.resolve({
          ok: false,
          status: 403,
          text: async () =>
            JSON.stringify({ error: "Path is outside the music library." }),
        }),
    });
    await renderLoaded();

    await fireEvent.input(screen.getByLabelText("Artist"), {
      target: { value: "New" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "Apply to 3 file(s)" }),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith(
        "Path is outside the music library.",
      ),
    );
    expect(field(screen.getByLabelText("Artist")).value).toBe("New");
  });

  it("shows an empty state for folders without audio", () => {
    stubFetch();
    render(BulkEditor, {
      props: {
        folderNode: { name: "e", path: "e", type: "directory", children: [] },
      },
    });

    expect(screen.getByText("No audio files in this folder.")).toBeTruthy();
  });
});
