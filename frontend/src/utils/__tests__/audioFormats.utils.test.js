import { describe, expect, it } from "vitest";

import {
  AUDIO_EXTENSIONS,
  AUDIO_FORMAT_LABELS,
  getAudioFormatLabel,
  getFileExtension,
  isAudioFile,
} from "../audioFormats.utils.js";

describe("audioFormats", () => {
  it("extracts lower-case extensions", () => {
    expect(getFileExtension("song.MP3")).toBe("mp3");
    expect(getFileExtension("archive.tar.gz")).toBe("gz");
    expect(getFileExtension("folder/song.flac")).toBe("flac");
    expect(getFileExtension("no-extension")).toBe("");
    expect(getFileExtension("")).toBe("");
  });

  it("recognises every registered audio extension", () => {
    for (const extension of AUDIO_EXTENSIONS) {
      expect(isAudioFile(`track${extension}`)).toBe(true);
      expect(isAudioFile(`TRACK${extension.toUpperCase()}`)).toBe(true);
    }
  });

  it("trusts the backend file type for audio", () => {
    expect(isAudioFile("track.bin", "audio")).toBe(true);
  });

  it("falls back to the extension when the type is not audio", () => {
    expect(isAudioFile("track.mp3", "other")).toBe(true);
    expect(isAudioFile("cover.jpg", "image")).toBe(false);
    expect(isAudioFile("notes", undefined)).toBe(false);
  });

  it("labels known and unknown formats", () => {
    expect(getAudioFormatLabel("song.mp3")).toBe("MP3");
    expect(getAudioFormatLabel("song.aif")).toBe("AIFF");
    expect(getAudioFormatLabel("song.oga")).toBe("OGG");
    expect(getAudioFormatLabel("song.opus")).toBe("OPUS");
    expect(getAudioFormatLabel("song.m4b")).toBe("M4B");
    expect(getAudioFormatLabel("song.xyz")).toBe("XYZ");
    expect(getAudioFormatLabel("song")).toBe("");
  });

  it("keeps the registry keys in sync with the extension list", () => {
    expect(AUDIO_EXTENSIONS).toHaveLength(
      Object.keys(AUDIO_FORMAT_LABELS).length,
    );
  });
});
