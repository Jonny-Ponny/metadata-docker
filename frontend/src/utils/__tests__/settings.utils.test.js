import { afterEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

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

describe("settings utils", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.documentElement.removeAttribute("style");
    document.querySelector('link[rel="icon"][type="image/svg+xml"]')?.remove();
  });

  it("starts from the defaults without saved settings", async () => {
    const { settings } = await import("../settings.utils.js");

    expect(get(settings)).toMatchObject({
      allowDeleteKey: true,
      enablePlayer: true,
      folderScheme: "[[YYYY]] - [ALBUMARTIST] - [ALBUM]",
      fileScheme: "[ALBUMARTIST] - [ALBUM] - [TRACK] - [TITLE]",
      uploadDuplicates: "skip-identical",
      recursiveOverview: false,
      holdApplyDuration: 800,
      holdTagDeleteDuration: 800,
      holdDeleteDuration: 1500,
      "color-primary": "#fd7d05",
    });
    expect(get(settings).overviewFields).toContain("title");
    expect(get(settings).overviewFields).toContain("picture");
    expect(get(settings).overviewFields).toContain("releaseType");
    expect(get(settings).overviewFields).toContain("comment");
    expect(get(settings).overviewFields).toContain("description");
  });

  it("sanitizes configured hold durations", async () => {
    const { HOLD_DURATION_MAX, HOLD_DURATION_MIN, sanitizeHoldDuration } =
      await import("../settings.utils.js");

    expect(sanitizeHoldDuration("1200", 800)).toBe(1200);
    expect(sanitizeHoldDuration(0, 800)).toBe(HOLD_DURATION_MIN);
    expect(sanitizeHoldDuration(99999, 800)).toBe(HOLD_DURATION_MAX);
    expect(sanitizeHoldDuration(undefined, 800)).toBe(800);
    expect(sanitizeHoldDuration("not a number", 800)).toBe(800);
  });

  it("clamps hold durations from storage", async () => {
    localStorage.setItem(
      "appSettings",
      JSON.stringify({
        holdApplyDuration: "fast",
        holdTagDeleteDuration: 10,
        holdDeleteDuration: 99999,
      }),
    );

    const { settings } = await import("../settings.utils.js");

    expect(get(settings).holdApplyDuration).toBe(800);
    expect(get(settings).holdTagDeleteDuration).toBe(200);
    expect(get(settings).holdDeleteDuration).toBe(5000);
  });

  it("merges saved settings and migrates old field names", async () => {
    localStorage.setItem(
      "appSettings",
      JSON.stringify({
        enablePlayer: false,
        overviewFields: ["year", "track", "disk", "year", "title"],
      }),
    );

    const { settings } = await import("../settings.utils.js");

    expect(get(settings).enablePlayer).toBe(false);
    expect(get(settings).overviewFields).toEqual([
      "date",
      "trackNumber",
      "diskNumber",
      "title",
    ]);
    expect(get(settings).folderScheme).toBe(
      "[[YYYY]] - [ALBUMARTIST] - [ALBUM]",
    );
  });

  it("falls back to the defaults for malformed saved JSON", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    localStorage.setItem("appSettings", "{not json");

    const { settings } = await import("../settings.utils.js");

    expect(get(settings).enablePlayer).toBe(true);
    expect(error).toHaveBeenCalledWith(
      "Failed to load settings:",
      expect.any(SyntaxError),
    );
  });

  it("saves to localStorage and applies the theme", async () => {
    const { settings, saveSettings } = await import("../settings.utils.js");
    const next = {
      ...get(settings),
      enablePlayer: false,
      "color-primary": "#123456",
    };

    saveSettings(next);

    expect(JSON.parse(localStorage.getItem("appSettings") ?? "{}")).toEqual(
      next,
    );
    expect(get(settings).enablePlayer).toBe(false);
    expect(
      document.documentElement.style.getPropertyValue("--color-primary"),
    ).toBe("#123456");
    expect(
      document.querySelector('link[rel="icon"][type="image/svg+xml"]'),
    ).toBeTruthy();
  });

  it("applies the default colours for missing values", async () => {
    const { applyThemeFromSettings } = await import("../settings.utils.js");

    applyThemeFromSettings({});

    expect(
      document.documentElement.style.getPropertyValue("--color-primary"),
    ).toBe("#fd7d05");
    expect(
      document.documentElement.style.getPropertyValue("--color-badge-image"),
    ).toBe("#6666ff");
  });

  it("posts the renaming scheme with the auth token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(200, { new_path: "folder/new name", renamed: true }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { applyRenamingScheme } = await import("../settings.utils.js");
    const { authToken } = await import("../../stores/auth.store.js");
    authToken.set("token-1");

    const result = await applyRenamingScheme(
      "[TITLE]",
      "folder/song.mp3",
      false,
      { replaceSpaces: true },
    );

    expect(result).toEqual({ new_path: "folder/new name", renamed: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/apply-renaming-scheme", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer token-1",
      },
      body: JSON.stringify({
        path: "folder/song.mp3",
        scheme: "[TITLE]",
        isFolder: false,
        replaceSpaces: true,
      }),
    });
  });

  it("reports the backend renaming error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(400, { error: "Invalid scheme" })),
    );
    const { applyRenamingScheme } = await import("../settings.utils.js");

    await expect(
      applyRenamingScheme("[TITLE]", "folder/song.mp3"),
    ).rejects.toThrow("Failed to apply renaming scheme: Invalid scheme");
  });

  it("wraps network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connection lost")),
    );
    const { applyRenamingScheme } = await import("../settings.utils.js");

    await expect(
      applyRenamingScheme("[TITLE]", "folder/song.mp3"),
    ).rejects.toThrow("Failed to apply renaming scheme: connection lost");
  });
});
