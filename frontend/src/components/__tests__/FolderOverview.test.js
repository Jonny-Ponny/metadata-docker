import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import FolderOverview from "../FolderOverview.svelte";
import { settings } from "../../utils/settings.utils.js";

const files = [
  { path: "folder/a.mp3", name: "a.mp3", relativePath: "a.mp3" },
  { path: "folder/b.mp3", name: "b.mp3", relativePath: "b.mp3" },
];

/** @type {Record<string, any>} */
let originalSettings;

/**
 * @param {Record<string, Record<string, unknown>>} metadataByPath
 * @param {Set<string>} [failing]
 */
function stubMetadata(metadataByPath, failing = new Set()) {
  const fetchMock = vi.fn(
    /**
     * @param {string} url
     */
    (url) => {
      const path = decodeURIComponent(
        new URL(url, "http://localhost").searchParams.get("path") ?? "",
      );
      if (failing.has(path)) {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: async () => ({}),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => metadataByPath[path] ?? {},
      });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("FolderOverview", () => {
  beforeEach(() => {
    originalSettings = get(settings);
    settings.set({ ...originalSettings, overviewFields: ["title", "picture"] });
  });

  afterEach(() => {
    settings.set(originalSettings);
    vi.unstubAllGlobals();
  });

  it("shows the empty state without fetching", () => {
    const fetchMock = stubMetadata({});

    render(FolderOverview, { props: { folderPath: "folder", audioFiles: [] } });

    expect(
      screen.getByText("All files have selected metadata fields"),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists the files with missing fields", async () => {
    const fetchMock = stubMetadata({
      "folder/a.mp3": { title: "A", picture: "data:image/png;base64,AAAA" },
      "folder/b.mp3": { title: "", picture: null },
    });

    render(FolderOverview, {
      props: { folderPath: "folder", audioFiles: files },
    });

    expect(
      await screen.findByText("1 of 2 files have missing fields"),
    ).toBeTruthy();
    expect(screen.getByText("b.mp3")).toBeTruthy();
    expect(screen.getByText("Title")).toBeTruthy();
    expect(screen.getByText("Cover Art")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/metadata?path=folder%2Fa.mp3&includePicture=false",
    );
  });

  it("checks release type, comment and description", async () => {
    settings.set({
      ...originalSettings,
      overviewFields: ["releaseType", "comment", "description"],
    });
    stubMetadata({
      "folder/a.mp3": { releaseType: "", comment: "", description: "" },
      "folder/b.mp3": {
        releaseType: "Album",
        comment: "Note",
        description: "Details",
      },
    });

    render(FolderOverview, {
      props: { folderPath: "folder", audioFiles: files },
    });

    expect(
      await screen.findByText("1 of 2 files have missing fields"),
    ).toBeTruthy();
    expect(screen.getByText("Release Type")).toBeTruthy();
    expect(screen.getByText("Comment")).toBeTruthy();
    expect(screen.getByText("Description")).toBeTruthy();
    expect(screen.getByText("a.mp3")).toBeTruthy();
    expect(screen.queryByText("b.mp3")).toBeNull();
  });

  it("counts files that failed to load separately", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    stubMetadata(
      {
        "folder/a.mp3": { title: "A", picture: "data:image/png;base64,AAAA" },
      },
      new Set(["folder/b.mp3"]),
    );

    render(FolderOverview, {
      props: { folderPath: "folder", audioFiles: files },
    });

    expect(
      await screen.findByText("0 of 2 files have missing fields"),
    ).toBeTruthy();
    expect(screen.getByText("(and 1 failed to load)")).toBeTruthy();
  });

  it("reports when every file is complete", async () => {
    stubMetadata({
      "folder/a.mp3": { title: "A", picture: "data:image/png;base64,AAAA" },
      "folder/b.mp3": { title: "B", hasPicture: true },
    });

    render(FolderOverview, {
      props: { folderPath: "folder", audioFiles: files },
    });

    expect(
      await screen.findByText("All files have selected metadata fields"),
    ).toBeTruthy();
    expect(screen.queryByText("Files with missing fields")).toBeNull();
  });

  it("refetches when refresh is clicked", async () => {
    const fetchMock = stubMetadata({
      "folder/a.mp3": { title: "A", picture: "data:image/png;base64,AAAA" },
      "folder/b.mp3": { title: "B", picture: "data:image/png;base64,BBBB" },
    });
    render(FolderOverview, {
      props: { folderPath: "folder", audioFiles: files },
    });
    await screen.findByText("All files have selected metadata fields");
    const initialCalls = fetchMock.mock.calls.length;

    await fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBe(initialCalls + files.length),
    );
  });
});
