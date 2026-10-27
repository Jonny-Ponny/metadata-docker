import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import SettingsModal from "../SettingsModal.svelte";
import { settings, defaultColors } from "../../utils/settings.utils.js";
import { toast } from "../../stores/toast.store.js";

const addons = [
  {
    id: "musicbrainz",
    name: "MusicBrainz",
    version: "1.2.0",
    description: "Album and song metadata",
    github: "https://github.com/example/musicbrainz",
    methods: ["search_songs", "search_albums"],
    required_env_vars: ["MB_TOKEN"],
  },
];

/**
 * @param {number} status
 * @param {Record<string, unknown>} body
 */
function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

/**
 * @param {unknown[]} [fetchers]
 * @param {number} [status]
 */
function stubAddons(fetchers = addons, status = 200) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      status === 200
        ? jsonResponse(200, { fetchers })
        : jsonResponse(status, { error: "Unavailable" }),
    );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** @type {Record<string, any>} */
let originalSettings;

describe("SettingsModal", () => {
  beforeEach(() => {
    originalSettings = get(settings);
  });

  afterEach(() => {
    settings.set(originalSettings);
    vi.unstubAllGlobals();
    toast.clear();
  });

  it("renders nothing and does not fetch while closed", () => {
    const fetchMock = stubAddons();

    render(SettingsModal, { props: { isOpen: false, onClose: vi.fn() } });

    expect(screen.queryByText("Settings")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("collapses the hold and upload sections by default", () => {
    stubAddons();
    const { container } = render(SettingsModal, {
      props: { isOpen: true, onClose: vi.fn() },
    });

    const headings = [...container.querySelectorAll("h3")].map(
      (heading) => heading.textContent?.trim() ?? "",
    );
    expect(headings.indexOf("Folder Overview")).toBeLessThan(
      headings.indexOf("Hold Durations"),
    );
    expect(headings.indexOf("Hold Durations")).toBeLessThan(
      headings.indexOf("Uploads"),
    );
    expect(headings.indexOf("Uploads")).toBeLessThan(
      headings.indexOf("Color Customization"),
    );

    const collapsibles = [
      ...container.querySelectorAll("details.settings-collapsible"),
    ];
    expect(collapsibles).toHaveLength(2);
    for (const section of collapsibles) {
      expect(section.hasAttribute("open")).toBe(false);
    }
  });

  it("loads and lists the available addons", async () => {
    stubAddons();

    render(SettingsModal, { props: { isOpen: true, onClose: vi.fn() } });

    expect(await screen.findByText("MusicBrainz")).toBeTruthy();
    expect(screen.getByText("(musicbrainz)")).toBeTruthy();
    expect(screen.getByText("v1.2.0")).toBeTruthy();
    expect(screen.getByText("Album and song metadata")).toBeTruthy();
    expect(
      screen.getByRole("link", {
        name: "https://github.com/example/musicbrainz",
      }),
    ).toBeTruthy();
    expect(screen.getByText("search_songs")).toBeTruthy();
    expect(screen.getByText("MB_TOKEN")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
  });

  it("reports an empty addon list", async () => {
    stubAddons([]);

    render(SettingsModal, { props: { isOpen: true, onClose: vi.fn() } });

    expect(await screen.findByText("No addons loaded.")).toBeTruthy();
  });

  it("reports addon load failures without retrying in a loop", async () => {
    const fetchMock = stubAddons([], 500);

    render(SettingsModal, { props: { isOpen: true, onClose: vi.fn() } });

    expect(
      await screen.findByText("Error: Failed to fetch addons (500)"),
    ).toBeTruthy();
    expect(get(toast).at(-1)?.message).toBe(
      "Error fetching addons:Failed to fetch addons (500)",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("saves the edited settings", async () => {
    stubAddons();
    const onClose = vi.fn();
    render(SettingsModal, { props: { isOpen: true, onClose } });

    await fireEvent.click(
      screen.getByRole("checkbox", { name: /audio player/i }),
    );
    await fireEvent.click(
      screen.getByRole("checkbox", { name: /Allow Delete key/i }),
    );
    await fireEvent.change(
      screen.getByLabelText("When the destination file already exists"),
      { target: { value: "keep-both" } },
    );
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Settings" }),
    );

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(get(settings).enablePlayer).toBe(false);
    expect(get(settings).allowDeleteKey).toBe(false);
    expect(get(settings).uploadDuplicates).toBe("keep-both");
    const saved = JSON.parse(localStorage.getItem("appSettings") ?? "{}");
    expect(saved.enablePlayer).toBe(false);
    expect(saved.uploadDuplicates).toBe("keep-both");
  });

  it("saves clamped hold durations", async () => {
    stubAddons();
    render(SettingsModal, { props: { isOpen: true, onClose: vi.fn() } });

    const apply = screen.getByLabelText(
      "Apply a tag or cover to the whole folder",
    );
    const fileDelete = screen.getByLabelText("Delete a file or folder");

    await fireEvent.input(apply, { target: { value: "50" } });
    await fireEvent.input(fileDelete, { target: { value: "9999" } });
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Settings" }),
    );

    expect(get(settings).holdApplyDuration).toBe(200);
    expect(get(settings).holdDeleteDuration).toBe(5000);
    expect(get(settings).holdTagDeleteDuration).toBe(800);
  });

  it("discards the edits on cancel and Escape", async () => {
    stubAddons();
    const onClose = vi.fn();
    render(SettingsModal, { props: { isOpen: true, onClose } });

    await fireEvent.click(
      screen.getByRole("checkbox", { name: /audio player/i }),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(get(settings).enablePlayer).toBe(true);
    expect(localStorage.getItem("appSettings")).toBeNull();

    await fireEvent.click(
      screen.getByRole("checkbox", { name: /audio player/i }),
    );
    await fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(2);
    expect(get(settings).enablePlayer).toBe(true);
  });

  it("previews the folder and file naming schemes", async () => {
    stubAddons();
    const { container } = render(SettingsModal, {
      props: { isOpen: true, onClose: vi.fn() },
    });
    const [folderInput, fileInput] = /** @type {HTMLInputElement[]} */ ([
      ...container.querySelectorAll(".scheme-input"),
    ]);

    await fireEvent.input(folderInput, { target: { value: "[YYYY]" } });

    await waitFor(() => expect(screen.getByText("2013")).toBeTruthy());

    await fireEvent.click(
      screen.getByRole("checkbox", {
        name: /Replace spaces with underscores when smart renaming files/i,
      }),
    );

    expect(
      screen.getByText("鬱P_-_悪巫山戯_-_12_-_THE_DYING_MESSAGE.flac"),
    ).toBeTruthy();
    expect(/** @type {HTMLInputElement} */ (fileInput).value).toContain(
      "[TITLE]",
    );
  });

  it("inserts a variable into the scheme", async () => {
    stubAddons();
    const { container } = render(SettingsModal, {
      props: { isOpen: true, onClose: vi.fn() },
    });
    const [folderInput] = /** @type {HTMLInputElement[]} */ ([
      ...container.querySelectorAll(".scheme-input"),
    ]);

    await fireEvent.input(folderInput, { target: { value: "" } });
    const titleButtons = screen.getAllByRole("button", { name: "[TITLE]" });
    await fireEvent.click(titleButtons[0]);

    expect(/** @type {HTMLInputElement} */ (folderInput).value).toBe("[TITLE]");
    await waitFor(() =>
      expect(screen.getByText("THE DYING MESSAGE")).toBeTruthy(),
    );
  });

  it("toggles an overview field and persists it", async () => {
    stubAddons();
    render(SettingsModal, { props: { isOpen: true, onClose: vi.fn() } });

    await fireEvent.click(screen.getByRole("checkbox", { name: "Cover Art" }));
    await fireEvent.click(
      screen.getByRole("button", { name: "Save Settings" }),
    );

    expect(get(settings).overviewFields).not.toContain("picture");
    expect(get(settings).overviewFields).toContain("title");
    const saved = JSON.parse(localStorage.getItem("appSettings") ?? "{}");
    expect(saved.overviewFields).not.toContain("picture");
  });

  it("resets the colours to their defaults", async () => {
    stubAddons();
    const { container } = render(SettingsModal, {
      props: { isOpen: true, onClose: vi.fn() },
    });
    const primary = /** @type {HTMLInputElement} */ (
      container.querySelector("#color-primary")
    );

    await fireEvent.input(primary, { target: { value: "#123456" } });
    expect(primary.value).toBe("#123456");

    await fireEvent.click(
      screen.getByRole("button", { name: "Reset colours to defaults" }),
    );

    expect(primary.value).toBe(defaultColors["color-primary"]);
  });

  it("closes from the header button and the overlay", async () => {
    stubAddons();
    const onClose = vi.fn();
    const { container } = render(SettingsModal, {
      props: { isOpen: true, onClose },
    });

    await fireEvent.click(screen.getByTitle("Close (Esc)"));
    const overlay = /** @type {HTMLElement} */ (
      container.querySelector(".settings-modal-overlay")
    );
    await fireEvent.click(overlay);

    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("does not close when the dialog body is clicked", async () => {
    stubAddons();
    const onClose = vi.fn();
    const { container } = render(SettingsModal, {
      props: { isOpen: true, onClose },
    });

    const dialog = /** @type {HTMLElement} */ (
      container.querySelector(".settings-modal")
    );
    await fireEvent.click(dialog);

    expect(onClose).not.toHaveBeenCalled();
  });
});
