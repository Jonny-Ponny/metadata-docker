import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import MetadataFetcher from "../MetadataFetcher.svelte";
import { toast } from "../../stores/toast.store.js";

const addon = {
  id: "musicbrainz",
  name: "MusicBrainz",
  methods: ["search_songs", "search_albums", "fetch_song", "fetch_album"],
};

const searchResults = [
  { id: "r1", title: "Search Title", artist: "Search Artist", date: "2020" },
  { id: "r2", title: "Second Result", artist: "Other Artist" },
];

const albumTracks = [
  { trackNumber: 1, title: "Track One", artist: "Album Artist" },
  { trackNumber: 2, title: "Track Two", artist: "Album Artist" },
];

const folderTree = [
  {
    path: "folder",
    type: "directory",
    children: [
      {
        path: "folder/a.mp3",
        name: "a.mp3",
        type: "file",
        file_type: "audio",
      },
      {
        path: "folder/b.mp3",
        name: "b.mp3",
        type: "file",
        file_type: "audio",
      },
      {
        path: "folder/cover.jpg",
        name: "cover.jpg",
        type: "file",
        file_type: "image",
      },
    ],
  },
];

/**
 * @param {unknown} body
 * @param {number} [status]
 */
function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

/**
 * @typedef {Object} ApiOverrides
 * @property {unknown[]} [fetchers]
 * @property {Record<string, unknown>} [metadata]
 * @property {unknown[]} [tree]
 * @property {Record<string, unknown>} [search]
 * @property {Record<string, unknown>} [song]
 * @property {Record<string, unknown>} [album]
 * @property {boolean} [searchError]
 * @property {boolean} [songError]
 */

/**
 * @param {ApiOverrides} [overrides]
 */
function stubApi(overrides = {}) {
  const fetchMock = vi.fn(
    /**
     * @param {string} url
     * @param {{ method?: string }} [options]
     */
    async (url, options = {}) => {
      const target = String(url);
      if (target === "/api/addons") {
        return jsonResponse({
          fetchers: overrides.fetchers ?? [addon],
        });
      }
      if (target.startsWith("/api/metadata?path=")) {
        return jsonResponse(
          overrides.metadata ?? { title: "Song Title", album: "Album Name" },
        );
      }
      if (target === "/api/files") {
        return jsonResponse(overrides.tree ?? []);
      }
      if (
        target.includes("/search_songs") ||
        target.includes("/search_albums")
      ) {
        if (overrides.searchError) {
          return jsonResponse({ error: "Search failed" }, 500);
        }
        return jsonResponse(
          overrides.search ?? { success: true, results: searchResults },
        );
      }
      if (target.includes("/fetch_song/")) {
        if (overrides.songError) {
          return jsonResponse({ error: "Nope" }, 500);
        }
        return jsonResponse(
          overrides.song ?? {
            success: true,
            metadata: {
              title: "Fetched Title",
              artist: "Fetched Artist",
              extraInfo: "Score 99",
            },
          },
        );
      }
      if (target.includes("/fetch_album/")) {
        return jsonResponse(
          overrides.album ?? { success: true, metadata: albumTracks },
        );
      }
      if (target === "/api/metadata/picture/url") {
        return jsonResponse({ success: true });
      }
      return jsonResponse({ success: true, options });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * @param {ApiOverrides} [overrides]
 */
async function renderSong(overrides = {}) {
  stubApi(overrides);
  render(MetadataFetcher, {
    props: {
      isOpen: true,
      onClose: vi.fn(),
      mode: "song",
      targetPath: "folder/song.mp3",
    },
  });
  await waitFor(() =>
    expect(
      /** @type {HTMLInputElement} */ (screen.getByPlaceholderText("Search..."))
        .value,
    ).toBe("Song Title"),
  );
}

/**
 * Render an album search and select the first result.
 * @param {Record<string, unknown>} [overrides]
 * @param {{ isFolder?: boolean, targetPath?: string }} [props]
 */
async function renderAlbum(overrides = {}, props = {}) {
  stubApi(overrides);
  const onClose = vi.fn();
  render(MetadataFetcher, {
    props: {
      isOpen: true,
      onClose,
      mode: "album",
      targetPath: props.targetPath ?? "folder/song.mp3",
      isFolder: props.isFolder ?? false,
    },
  });
  await waitFor(() =>
    expect(
      /** @type {HTMLInputElement} */ (screen.getByPlaceholderText("Search..."))
        .value,
    ).toBe("Album Name"),
  );
  await fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await fireEvent.click(await screen.findByText("Search Title"));
  return onClose;
}

describe("MetadataFetcher", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    toast.clear();
  });

  it("renders nothing while closed", () => {
    const fetchMock = stubApi();

    render(MetadataFetcher, {
      props: {
        isOpen: false,
        onClose: vi.fn(),
        mode: "song",
        targetPath: "folder/song.mp3",
      },
    });

    expect(screen.queryByText("Fetch Song Metadata")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads addons and prefills the song query", async () => {
    await renderSong();

    expect(screen.getByText("Fetch Song Metadata")).toBeTruthy();
    expect(
      /** @type {HTMLSelectElement} */ (screen.getByRole("combobox")).value,
    ).toBe("musicbrainz");
    expect(document.activeElement).toBe(
      screen.getByPlaceholderText("Search..."),
    );
    expect(localStorage.getItem("md_lastAddonId")).toBe("musicbrainz");
  });

  it("keeps the last used addon when it is still available", async () => {
    localStorage.setItem("md_lastAddonId", "musicbrainz");
    const second = { ...addon, id: "other", name: "Other" };
    stubApi({ fetchers: [second, addon] });

    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "song",
        targetPath: "folder/song.mp3",
      },
    });

    await waitFor(() =>
      expect(
        /** @type {HTMLSelectElement} */ (screen.getByRole("combobox")).value,
      ).toBe("musicbrainz"),
    );
  });

  it("warns when no addon supports the mode", async () => {
    stubApi({
      fetchers: [{ id: "x", name: "X", methods: ["search_songs"] }],
    });

    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "album",
        targetPath: "folder/song.mp3",
      },
    });

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe(
        "No addon supports search_albums",
      ),
    );
    expect(
      /** @type {HTMLButtonElement} */ (
        screen.getByRole("button", { name: "Search" })
      ).disabled,
    ).toBe(true);
  });

  it("requires a query before searching", async () => {
    await renderSong();
    const query = screen.getByPlaceholderText("Search...");
    await fireEvent.input(query, { target: { value: "  " } });

    await fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(get(toast).at(-1)?.message).toBe(
      "Please select an add‑on and enter a query",
    );
  });

  it("lists search results and reports an empty result set", async () => {
    await renderSong({ search: { success: true, results: [] } });

    await fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("No results found"),
    );
  });

  it("shows the search results with their extra info", async () => {
    await renderSong({
      search: {
        success: true,
        results: [{ ...searchResults[0], extraInfo: "MusicBrainz score 100" }],
      },
    });

    await fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Search Title")).toBeTruthy();
    expect(screen.getByText("MusicBrainz score 100")).toBeTruthy();
  });

  it("reports a failed search", async () => {
    await renderSong({ searchError: true });

    await fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("Search error: Search failed"),
    );
  });

  it("previews the fetched song metadata", async () => {
    await renderSong();
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));

    expect(await screen.findByText("Song Metadata")).toBeTruthy();
    expect(screen.getByText("Fetched Title")).toBeTruthy();
    expect(screen.getByText("Fetched Artist")).toBeTruthy();
    expect(screen.getByText("Score 99")).toBeTruthy();
    expect(
      /** @type {HTMLInputElement} */ (screen.getByLabelText(/Title:/)).checked,
    ).toBe(true);
  });

  it("reports a failed metadata fetch", async () => {
    await renderSong({ songError: true });
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe(
        "Fetch error: Failed to fetch metadata",
      ),
    );
  });

  it("applies the selected song fields and refreshes the views", async () => {
    stubApi();
    const fetchMock = /** @type {ReturnType<typeof vi.fn>} */ (
      globalThis.fetch
    );
    const refreshTree = vi.fn();
    const refreshMetadata = vi.fn();
    const onClose = vi.fn();
    window.addEventListener("refreshFileTree", refreshTree);
    window.addEventListener("refreshMetadata", refreshMetadata);
    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose,
        mode: "song",
        targetPath: "folder/song.mp3",
      },
    });
    await waitFor(() =>
      expect(
        /** @type {HTMLInputElement} */ (
          screen.getByPlaceholderText("Search...")
        ).value,
      ).toBe("Song Title"),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));
    await screen.findByText("Song Metadata");

    await fireEvent.click(
      screen.getByRole("button", { name: "Apply Selected" }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/metadata/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "folder/song.mp3",
          field: "title",
          value: "Fetched Title",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith("/api/metadata/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: "folder/song.mp3",
        field: "artist",
        value: "Fetched Artist",
      }),
    });
    expect(refreshTree).toHaveBeenCalled();
    expect(refreshMetadata).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();

    window.removeEventListener("refreshFileTree", refreshTree);
    window.removeEventListener("refreshMetadata", refreshMetadata);
  });

  it("uploads a remote cover URL instead of writing a tag", async () => {
    await renderSong({
      song: {
        success: true,
        metadata: { title: "Fetched Title", picture: "https://img.test/a.jpg" },
      },
    });
    const fetchMock = /** @type {ReturnType<typeof vi.fn>} */ (
      globalThis.fetch
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));
    await screen.findByText("Song Metadata");

    await fireEvent.click(
      screen.getByRole("button", { name: "Apply Selected" }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/metadata/picture/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "folder/song.mp3",
          url: "https://img.test/a.jpg",
        }),
      }),
    );
  });

  it("previews an album and switches the selected track", async () => {
    stubApi();
    const { container } = render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "album",
        targetPath: "folder/song.mp3",
      },
    });
    await waitFor(() =>
      expect(
        /** @type {HTMLInputElement} */ (
          screen.getByPlaceholderText("Search...")
        ).value,
      ).toBe("Album Name"),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));

    expect(await screen.findByText("Track Metadata")).toBeTruthy();
    expect(screen.getByText("Track One")).toBeTruthy();

    const trackSelect = /** @type {HTMLSelectElement} */ (
      container.querySelector(".track-selector select")
    );
    await fireEvent.change(trackSelect, { target: { value: "1" } });

    await waitFor(() => expect(screen.getByText("Track Two")).toBeTruthy());
    expect(
      /** @type {HTMLInputElement} */ (screen.getByLabelText(/Title:/)).checked,
    ).toBe(true);
  });

  it("warns when an album has no tracks", async () => {
    await renderAlbum({ album: { success: true, metadata: [] } });

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("No tracks found in album"),
    );
  });

  it("batch-matches folder files to album tracks", async () => {
    stubApi({ tree: folderTree });
    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "album",
        targetPath: "folder",
        isFolder: true,
      },
    });
    await waitFor(() =>
      expect(
        /** @type {HTMLInputElement} */ (
          screen.getByPlaceholderText("Search...")
        ).value,
      ).toBe("Album Name"),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));

    expect(await screen.findByText("Files in folder")).toBeTruthy();
    expect(screen.getByText("a.mp3")).toBeTruthy();
    expect(screen.getByText("b.mp3")).toBeTruthy();
    expect(screen.queryByText("cover.jpg")).toBeNull();
    expect(screen.getAllByText("Global filter").length).toBe(1);
  });

  it("applies the batch selection to every enabled file", async () => {
    stubApi({ tree: folderTree });
    const fetchMock = /** @type {ReturnType<typeof vi.fn>} */ (
      globalThis.fetch
    );
    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "album",
        targetPath: "folder",
        isFolder: true,
      },
    });
    await waitFor(() =>
      expect(
        /** @type {HTMLInputElement} */ (
          screen.getByPlaceholderText("Search...")
        ).value,
      ).toBe("Album Name"),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));
    await screen.findByText("Files in folder");

    await fireEvent.click(
      screen.getByRole("button", { name: "Apply Selected" }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/metadata/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "folder/a.mp3",
          field: "title",
          value: "Track One",
        }),
      }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/metadata/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "folder/b.mp3",
          field: "title",
          value: "Track Two",
        }),
      }),
    );
    expect(get(toast).at(-1)?.message).toBe("Metadata applied to 2 file(s)");
  });

  it("skips every file after the None preset", async () => {
    stubApi({ tree: folderTree });
    const fetchMock = /** @type {ReturnType<typeof vi.fn>} */ (
      globalThis.fetch
    );
    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "album",
        targetPath: "folder",
        isFolder: true,
      },
    });
    await waitFor(() =>
      expect(
        /** @type {HTMLInputElement} */ (
          screen.getByPlaceholderText("Search...")
        ).value,
      ).toBe("Album Name"),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await fireEvent.click(await screen.findByText("Search Title"));
    await screen.findByText("Files in folder");
    await fireEvent.click(screen.getByRole("button", { name: "None" }));

    await fireEvent.click(
      screen.getByRole("button", { name: "Apply Selected" }),
    );

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("Metadata applied to 0 file(s)"),
    );
    expect(
      fetchMock.mock.calls.filter(
        ([url]) => String(url) === "/api/metadata/file",
      ),
    ).toHaveLength(0);
  });

  it("warns when the folder has no audio files", async () => {
    stubApi({
      tree: [
        {
          path: "folder",
          type: "directory",
          children: [
            {
              path: "folder/cover.jpg",
              name: "cover.jpg",
              type: "file",
              file_type: "image",
            },
          ],
        },
      ],
    });
    render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose: vi.fn(),
        mode: "album",
        targetPath: "folder",
        isFolder: true,
      },
    });

    await waitFor(() =>
      expect(get(toast).at(-1)?.message).toBe("No audio files found in folder"),
    );
  });

  it("closes from the close button, cancel button and overlay", async () => {
    stubApi();
    const onClose = vi.fn();
    const { container } = render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose,
        mode: "song",
        targetPath: "folder/song.mp3",
      },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Search" })).toBeTruthy(),
    );

    await fireEvent.click(screen.getByRole("button", { name: "✕" }));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".modal-overlay")
    );
    await fireEvent.click(overlay);

    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("does not close when the dialog body is clicked", async () => {
    stubApi();
    const onClose = vi.fn();
    const { container } = render(MetadataFetcher, {
      props: {
        isOpen: true,
        onClose,
        mode: "song",
        targetPath: "folder/song.mp3",
      },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Search" })).toBeTruthy(),
    );

    const dialog = /** @type {HTMLElement} */ (
      container.querySelector(".modal-container")
    );
    await fireEvent.click(dialog);

    expect(onClose).not.toHaveBeenCalled();
  });
});
