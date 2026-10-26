import { describe, expect, it } from "vitest";
import {
  TIMESTAMP_PLACEHOLDER,
  buildLrc,
  parseLrc,
  processEditedLyrics,
  shiftTimestamps,
} from "../lyrics.utils.js";

describe("parseLrc", () => {
  it("separates ID tags from timed lyric lines", () => {
    const result = parseLrc(
      "[ti:Song]\n[ar:Artist]\n[al:Album]\n[00:01.00]Hello\n[00:02.50]World",
    );

    expect(result).toEqual({
      text: "Hello\nWorld",
      timestamps: ["[00:01.00]", "[00:02.50]"],
      headers: { ti: "Song", ar: "Artist", al: "Album" },
      hasOffset: false,
    });
  });

  it("handles a BOM and CRLF line endings", () => {
    const result = parseLrc("\uFEFF[00:01.00]One\r\n[00:02.00]Two");

    expect(result.text).toBe("One\nTwo");
    expect(result.timestamps).toEqual(["[00:01.00]", "[00:02.00]"]);
  });

  it("keeps blank and untimed lines aligned with a placeholder", () => {
    const result = parseLrc("  indented\n\nplain text");

    expect(result.text).toBe("  indented\n\nplain text");
    expect(result.timestamps).toEqual([
      TIMESTAMP_PLACEHOLDER,
      TIMESTAMP_PLACEHOLDER,
      TIMESTAMP_PLACEHOLDER,
    ]);
  });

  it("expands a line with several timestamps into several entries", () => {
    const result = parseLrc(
      "[00:10.00][01:00.00]Chorus\n[00:20.00]Verse",
    );

    expect(result.text).toBe("Chorus\nChorus\nVerse");
    expect(result.timestamps).toEqual([
      "[00:10.00]",
      "[01:00.00]",
      "[00:20.00]",
    ]);
  });

  it("normalises comma decimals and decimal precision", () => {
    const result = parseLrc("[00:01,5]A\n[00:01.234]B");

    expect(result.text).toBe("A\nB");
    expect(result.timestamps).toEqual(["[00:01.50]", "[00:01.23]"]);
  });

  it("carries a rounded timestamp into the next minute", () => {
    expect(parseLrc("[00:59.999]Roll").timestamps).toEqual(["[01:00.00]"]);
  });

  it("treats its own placeholder as an untimed line", () => {
    expect(parseLrc("[--:--.--]Untimed")).toEqual({
      text: "Untimed",
      timestamps: [TIMESTAMP_PLACEHOLDER],
      headers: {},
      hasOffset: false,
    });
    expect(parseLrc("[--:--.--]").text).toBe("");
  });

  it("detects the offset header and lower-cases the key", () => {
    const result = parseLrc("[offset:500]");

    expect(result.headers).toEqual({ offset: "500" });
    expect(result.hasOffset).toBe(true);
    expect(result.text).toBe("");
  });

  it("does not mistake unknown bracket tags for metadata", () => {
    const result = parseLrc("[xx:not-a-tag]\n[00:01.00]Line");

    expect(result.headers).toEqual({});
    expect(result.text).toBe("[xx:not-a-tag]\nLine");
    expect(result.timestamps).toEqual([
      TIMESTAMP_PLACEHOLDER,
      "[00:01.00]",
    ]);
  });

  it("accepts single-digit seconds and one to three minute digits", () => {
    const result = parseLrc("[0:1.5]Short\n[100:00.00]Long");

    expect(result.timestamps).toEqual(["[00:01.50]", "[100:00.00]"]);
  });

  it("returns one empty line for empty input", () => {
    expect(parseLrc("")).toEqual({
      text: "",
      timestamps: [TIMESTAMP_PLACEHOLDER],
      headers: {},
      hasOffset: false,
    });
    expect(parseLrc(null).text).toBe("");
  });
});

describe("buildLrc", () => {
  it("writes only the non-empty headers in a fixed order", () => {
    const result = buildLrc([], [], {
      title: "Song",
      artist: "",
      album: "Album",
    });

    expect(result).toBe("[ti:Song]\n[al:Album]");
  });

  it("collapses newlines in header values", () => {
    expect(buildLrc([], [], { title: " Line\nBreak " })).toBe(
      "[ti:Line Break]",
    );
  });

  it("writes timed, untimed and empty lines", () => {
    const result = buildLrc(
      ["Hello", "Untimed", ""],
      ["[00:01.00]", TIMESTAMP_PLACEHOLDER, "[00:03.00]"],
    );

    expect(result).toBe("[00:01.00] Hello\nUntimed\n[00:03.00]");
  });

  it("writes a plain line when the timestamp is missing", () => {
    expect(buildLrc(["Hello"], [])).toBe("Hello");
  });

  it("returns an empty string for no content", () => {
    expect(buildLrc([], [], {})).toBe("");
  });
});

describe("shiftTimestamps", () => {
  it("shifts real timestamps and keeps placeholders", () => {
    const result = shiftTimestamps(
      ["[00:01.00]", TIMESTAMP_PLACEHOLDER, "[00:10.00]"],
      1.25,
    );

    expect(result).toEqual({
      ok: true,
      count: 2,
      error: "",
      timestamps: ["[00:02.25]", TIMESTAMP_PLACEHOLDER, "[00:11.25]"],
    });
  });

  it("returns a copy when there is nothing to shift", () => {
    const input = [TIMESTAMP_PLACEHOLDER];
    const result = shiftTimestamps(input, 5);

    expect(result.ok).toBe(true);
    expect(result.count).toBe(0);
    expect(result.timestamps).toEqual(input);
    expect(result.timestamps).not.toBe(input);
  });

  it("returns a copy for a zero offset", () => {
    const input = ["[00:01.00]"];
    const result = shiftTimestamps(input, 0);

    expect(result.ok).toBe(true);
    expect(result.count).toBe(1);
    expect(result.timestamps).toEqual(input);
    expect(result.timestamps).not.toBe(input);
  });

  it("rejects an invalid offset", () => {
    const result = shiftTimestamps(["[00:01.00]"], Number.NaN);

    expect(result.ok).toBe(false);
    expect(result.count).toBe(0);
    expect(result.error).toBe("Invalid shift amount");
    expect(result.timestamps).toEqual(["[00:01.00]"]);
  });

  it("rejects a shift before 00:00.00", () => {
    const result = shiftTimestamps(["[00:01.50]"], -1.6);

    expect(result.ok).toBe(false);
    expect(result.count).toBe(1);
    expect(result.error).toBe(
      "Cannot shift earlier than 00:00.00 (max -1.50s)",
    );
    expect(result.timestamps).toEqual(["[00:01.50]"]);
  });

  it("allows a shift that lands exactly on 00:00.00", () => {
    const result = shiftTimestamps(["[00:01.50]"], -1.5);

    expect(result.ok).toBe(true);
    expect(result.timestamps).toEqual(["[00:00.00]"]);
  });
});

describe("processEditedLyrics", () => {
  it("returns the processed text and timestamps", () => {
    expect(processEditedLyrics("[00:01.00]Hello")).toEqual({
      text: "Hello",
      timestamps: ["[00:01.00]"],
    });
  });
});
