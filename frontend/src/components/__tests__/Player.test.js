import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";
import { get } from "svelte/store";

import Player from "../Player.svelte";
import { settings } from "../../utils/settings.utils.js";

class FakeAudio {
  /** @type {FakeAudio[]} */
  static instances = [];

  /** @type {Map<string, (() => void)[]>} */
  listeners = new Map();

  constructor() {
    this.src = "";
    this.currentTime = 0;
    this.duration = 0;
    this.volume = 1;
    this.readyState = 0;
    /** @type {{ code: number } | null} */
    this.error = null;
    this.play = vi.fn().mockResolvedValue(undefined);
    this.pause = vi.fn();
    this.load = vi.fn();
    FakeAudio.instances.push(this);
  }

  /**
   * @param {string} type
   * @param {() => void} listener
   */
  addEventListener(type, listener) {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  /**
   * @param {string} type
   * @param {() => void} listener
   */
  removeEventListener(type, listener) {
    this.listeners.set(
      type,
      (this.listeners.get(type) ?? []).filter((item) => item !== listener),
    );
  }

  /**
   * @param {string} type
   */
  emit(type) {
    for (const listener of this.listeners.get(type) ?? []) listener();
  }
}

const audioFile = {
  url: "/api/audio?token=abc",
  name: "song.mp3",
  type: "audio/mpeg",
};

/** @type {Record<string, any>} */
let originalSettings;

describe("Player", () => {
  beforeEach(() => {
    FakeAudio.instances = [];
    vi.stubGlobal("Audio", FakeAudio);
    originalSettings = get(settings);
    settings.set({ ...originalSettings, enablePlayer: true });
  });

  afterEach(() => {
    settings.set(originalSettings);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /**
   * @returns {FakeAudio}
   */
  function currentAudio() {
    const audio = FakeAudio.instances.at(-1);
    if (!audio) throw new Error("Audio element was not created");
    return audio;
  }

  it("starts with no file and a disabled play button", () => {
    render(Player, { props: { audioFile: null } });

    expect(screen.getByText("No file loaded")).toBeTruthy();
    const button = screen.getByTitle("Play");
    expect(/** @type {HTMLButtonElement} */ (button).disabled).toBe(true);
  });

  it("shows the filename and toggles playback", async () => {
    render(Player, { props: { audioFile } });
    const audio = currentAudio();

    expect(screen.getByText("song.mp3")).toBeTruthy();
    await fireEvent.click(screen.getByTitle("Play"));

    await waitFor(() => expect(screen.getByTitle("Pause")).toBeTruthy());
    expect(audio.src).toBe(audioFile.url);
    expect(audio.play).toHaveBeenCalledTimes(1);
    expect(audio.volume).toBeCloseTo(0.05);

    await fireEvent.click(screen.getByTitle("Pause"));

    expect(audio.pause).toHaveBeenCalledTimes(1);
    expect(screen.getByTitle("Play")).toBeTruthy();
  });

  it("updates the clock on timeupdate and notifies the parent", async () => {
    const ontimeupdate = vi.fn();
    render(Player, { props: { audioFile, ontimeupdate } });
    const audio = currentAudio();
    audio.duration = 100;
    audio.currentTime = 65;
    audio.emit("loadedmetadata");
    audio.emit("timeupdate");

    await waitFor(() => expect(screen.getByText("1:05 / 1:40")).toBeTruthy());
    expect(ontimeupdate).toHaveBeenCalledWith(65);
  });

  it("seeks from a click on the progress bar", async () => {
    const ontimeupdate = vi.fn();
    const { container } = render(Player, {
      props: { audioFile, ontimeupdate },
    });
    const audio = currentAudio();
    audio.duration = 200;
    audio.emit("loadedmetadata");
    const progress = /** @type {HTMLElement} */ (
      container.querySelector(".progress-bar")
    );
    progress.getBoundingClientRect = () =>
      /** @type {DOMRect} */ ({ left: 0, width: 200, top: 0, height: 3 });

    await fireEvent.click(progress, { clientX: 50 });

    expect(audio.currentTime).toBe(50);
    expect(ontimeupdate).toHaveBeenCalledWith(50);
  });

  it("seeks on a lyrics-seek event", async () => {
    const ontimeupdate = vi.fn();
    render(Player, { props: { audioFile, ontimeupdate } });
    const audio = currentAudio();
    audio.duration = 100;
    audio.emit("loadedmetadata");

    window.dispatchEvent(
      new CustomEvent("lyrics-seek", { detail: { time: 42 } }),
    );

    expect(audio.currentTime).toBe(42);
    expect(audio.play).toHaveBeenCalled();
    expect(ontimeupdate).toHaveBeenCalledWith(42);
  });

  it("loads and saves the volume", async () => {
    localStorage.setItem("player-volume", "0.3");
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    const slider = /** @type {HTMLInputElement} */ (screen.getByRole("slider"));

    expect(audio.volume).toBeCloseTo(0.3);
    expect(slider.value).toBe("0.3");

    await fireEvent.input(slider, { target: { value: "0.5" } });

    expect(audio.volume).toBeCloseTo(0.5);
    expect(localStorage.getItem("player-volume")).toBe("0.5");
  });

  it("disables every control when the player is off in settings", () => {
    settings.set({ ...originalSettings, enablePlayer: false });

    render(Player, { props: { audioFile } });

    expect(screen.getByText("Player Disabled")).toBeTruthy();
    expect(
      /** @type {HTMLButtonElement} */ (
        screen.getByTitle(/player is disabled/i)
      ).disabled,
    ).toBe(true);
    expect(
      /** @type {HTMLInputElement} */ (screen.getByRole("slider")).disabled,
    ).toBe(true);
  });

  it("falls back to the default volume for saved invalid values", () => {
    for (const saved of ["loud", "-0.5", "1.5"]) {
      localStorage.setItem("player-volume", saved);
      const { unmount } = render(Player, { props: { audioFile } });
      expect(currentAudio().volume).toBeCloseTo(0.05);
      unmount();
      FakeAudio.instances = [];
    }
  });

  it("logs when the saved volume cannot be read", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    render(Player, { props: { audioFile } });

    expect(consoleSpy).toHaveBeenCalledWith(
      "[Player] Failed to load volume from localStorage:",
      expect.any(Error),
    );
    expect(currentAudio().volume).toBeCloseTo(0.05);
  });

  it("logs when the volume cannot be saved", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(Player, { props: { audioFile } });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("full");
    });

    await fireEvent.input(screen.getByRole("slider"), {
      target: { value: "0.4" },
    });

    expect(consoleSpy).toHaveBeenCalledWith(
      "[Player] Failed to save volume to localStorage:",
      expect.any(Error),
    );
  });

  it("changes the volume with the wheel and clamps it", async () => {
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    const slider = /** @type {HTMLInputElement} */ (screen.getByRole("slider"));

    await fireEvent.wheel(slider, { deltaY: -100 });

    expect(audio.volume).toBeCloseTo(0.1);
    expect(slider.value).toBe("0.1");
    expect(localStorage.getItem("player-volume")).toBe("0.1");

    await fireEvent.wheel(slider, { deltaY: 100 });
    await fireEvent.wheel(slider, { deltaY: 100 });

    expect(audio.volume).toBe(0);
    expect(slider.value).toBe("0");

    await fireEvent.input(slider, { target: { value: "0.98" } });
    await fireEvent.wheel(slider, { deltaY: -100 });
    await fireEvent.wheel(slider, { deltaY: -100 });

    expect(audio.volume).toBe(1);
  });

  it("ignores the volume wheel while the player is disabled", async () => {
    settings.set({ ...originalSettings, enablePlayer: false });
    render(Player, { props: { audioFile } });
    const audio = currentAudio();

    await fireEvent.wheel(screen.getByRole("slider"), { deltaY: -100 });

    expect(audio.volume).toBeCloseTo(0.05);
    expect(localStorage.getItem("player-volume")).toBeNull();
  });

  it("reports a playback failure and stays paused", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    audio.play.mockRejectedValueOnce(new Error("blocked"));

    await fireEvent.click(screen.getByTitle("Play"));

    await waitFor(() =>
      expect(consoleSpy).toHaveBeenCalledWith(
        "[Player] Playback failed:",
        expect.any(Error),
      ),
    );
    expect(screen.getByTitle("Play")).toBeTruthy();
  });

  it("auto-plays the next file after a track change while playing", async () => {
    const { rerender } = render(Player, { props: { audioFile } });
    const audio = currentAudio();

    await fireEvent.click(screen.getByTitle("Play"));
    await waitFor(() => expect(screen.getByTitle("Pause")).toBeTruthy());

    await rerender({
      audioFile: {
        ...audioFile,
        url: "/api/audio?token=next",
        name: "next.mp3",
      },
    });
    audio.emit("loadedmetadata");

    await waitFor(() => expect(screen.getByTitle("Pause")).toBeTruthy());
    expect(audio.src).toBe("/api/audio?token=next");
    expect(audio.play).toHaveBeenCalledTimes(2);
  });

  it("logs a failed auto-play after a track change", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(Player, { props: { audioFile } });
    const audio = currentAudio();

    await fireEvent.click(screen.getByTitle("Play"));
    audio.play.mockRejectedValueOnce(new Error("blocked"));
    await rerender({
      audioFile: {
        ...audioFile,
        url: "/api/audio?token=next",
        name: "next.mp3",
      },
    });
    audio.emit("loadedmetadata");

    await waitFor(() =>
      expect(consoleSpy).toHaveBeenCalledWith(
        "[Player] Auto-play failed:",
        expect.any(Error),
      ),
    );
    expect(screen.getByTitle("Play")).toBeTruthy();
  });

  it("does not auto-play a track change while paused", async () => {
    const { rerender } = render(Player, { props: { audioFile } });
    const audio = currentAudio();

    await rerender({
      audioFile: {
        ...audioFile,
        url: "/api/audio?token=next",
        name: "next.mp3",
      },
    });
    audio.emit("loadedmetadata");

    expect(audio.play).not.toHaveBeenCalled();
    expect(screen.getByTitle("Play")).toBeTruthy();
  });

  it("resets the clock after the track ends", async () => {
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    await fireEvent.click(screen.getByTitle("Play"));
    await waitFor(() => expect(screen.getByTitle("Pause")).toBeTruthy());
    audio.duration = 100;
    audio.emit("loadedmetadata");

    audio.emit("ended");

    await waitFor(() => expect(screen.getByTitle("Play")).toBeTruthy());
  });

  it("logs an audio element error", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    audio.error = { code: 4 };

    audio.emit("error");

    expect(consoleSpy).toHaveBeenCalledWith("[Player] Audio error:", {
      code: 4,
    });
  });

  it("broadcasts time updates and answers get-current-time", async () => {
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    const timeListener = vi.fn();
    const timeCallback = vi.fn();
    window.addEventListener("player-time-update", timeListener);

    audio.currentTime = 12.5;
    audio.emit("timeupdate");
    window.dispatchEvent(
      new CustomEvent("get-current-time", {
        detail: { callback: timeCallback },
      }),
    );
    await tick();

    expect(timeListener).toHaveBeenCalled();
    expect(
      /** @type {CustomEvent<{time: number}>} */ (timeListener.mock.calls[0][0])
        .detail.time,
    ).toBe(12.5);
    expect(timeCallback).toHaveBeenCalledWith(12.5);
    window.removeEventListener("player-time-update", timeListener);
  });

  it("answers get-current-time with the live position, not the last timeupdate", () => {
    render(Player, { props: { audioFile } });
    const audio = currentAudio();
    const timeCallback = vi.fn();

    audio.currentTime = 12.5;
    audio.emit("timeupdate");

    // Playback moved on, but the browser has not fired the next timeupdate yet.
    audio.currentTime = 12.7;
    window.dispatchEvent(
      new CustomEvent("get-current-time", {
        detail: { callback: timeCallback },
      }),
    );

    expect(timeCallback).toHaveBeenCalledWith(12.7);
  });

  it("clamps a seek to the track duration", () => {
    const ontimeupdate = vi.fn();
    const { component } = render(Player, {
      props: { audioFile, ontimeupdate },
    });
    const audio = currentAudio();
    audio.duration = 100;
    audio.emit("loadedmetadata");

    component.seekToTime(999);

    expect(audio.currentTime).toBe(100);
    expect(ontimeupdate).toHaveBeenCalledWith(100);
  });

  it("performs a seek requested before the metadata loads", async () => {
    const ontimeupdate = vi.fn();
    const { component } = render(Player, {
      props: { audioFile, ontimeupdate },
    });
    const audio = currentAudio();
    await tick();

    // The duration is still unknown, so the seek is queued.
    expect(component.seekToTime(42)).toBe(true);
    expect(audio.currentTime).toBe(0);

    audio.duration = 100;
    audio.emit("loadedmetadata");
    await tick();

    expect(audio.currentTime).toBe(42);
    expect(audio.play).toHaveBeenCalled();
    expect(ontimeupdate).toHaveBeenCalledWith(42);
  });

  it("refuses to seek without a file", () => {
    const { component } = render(Player, { props: { audioFile: null } });

    expect(component.seekToTime(10)).toBe(false);
  });

  it("stops playback and clears the track", async () => {
    const { component } = render(Player, { props: { audioFile } });
    const audio = currentAudio();
    await fireEvent.click(screen.getByTitle("Play"));
    audio.currentTime = 40;
    audio.duration = 100;
    audio.emit("timeupdate");

    component.stop();

    expect(audio.pause).toHaveBeenCalled();
    expect(audio.src).toBe("");
    expect(audio.load).toHaveBeenCalled();
    expect(component.getCurrentTime()).toBe(0);
    expect(screen.getByText("00:00 / 00:00")).toBeTruthy();
  });

  it("does not seek without a duration or while disabled", async () => {
    const ontimeupdate = vi.fn();
    const { container, unmount } = render(Player, {
      props: { audioFile, ontimeupdate },
    });
    const audio = currentAudio();
    const progress = /** @type {HTMLElement} */ (
      container.querySelector(".progress-bar")
    );

    await fireEvent.click(progress, { clientX: 50 });
    expect(audio.currentTime).toBe(0);
    expect(ontimeupdate).not.toHaveBeenCalled();

    unmount();
    settings.set({ ...originalSettings, enablePlayer: false });
    const disabled = render(Player, { props: { audioFile, ontimeupdate } });
    const disabledAudio = currentAudio();
    disabledAudio.duration = 100;
    disabledAudio.emit("loadedmetadata");

    await fireEvent.click(
      /** @type {HTMLElement} */ (
        disabled.container.querySelector(".progress-bar")
      ),
      { clientX: 50 },
    );

    expect(disabledAudio.currentTime).toBe(0);
    expect(ontimeupdate).not.toHaveBeenCalled();
  });
});
