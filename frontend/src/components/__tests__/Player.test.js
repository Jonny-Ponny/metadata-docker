import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
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
});
