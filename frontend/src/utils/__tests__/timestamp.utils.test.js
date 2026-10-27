// @ts-check
import { describe, expect, it } from "vitest";
import {
  formatTimeDisplay,
  parseTimestampToSeconds,
  secondsToTimestamp,
  validateTimestampFormat,
  validateTimestampRange,
} from "../timestamp.utils.js";

describe("parseTimestampToSeconds", () => {
  it("parses a bracketed LRC timestamp", () => {
    expect(parseTimestampToSeconds("[01:02.50]")).toBe(62.5);
    expect(parseTimestampToSeconds("[00:00.00]")).toBe(0);
    expect(parseTimestampToSeconds("[100:00.00]")).toBe(6000);
  });

  it("parses one and three decimal digits", () => {
    expect(parseTimestampToSeconds("[00:01.5]")).toBe(1.5);
    expect(parseTimestampToSeconds("[00:01.234]")).toBe(1.234);
  });

  it("returns 0 for placeholders and malformed values", () => {
    expect(parseTimestampToSeconds("[--:--.--]")).toBe(0);
    expect(parseTimestampToSeconds("[01:02:03]")).toBe(0);
    expect(parseTimestampToSeconds("[a:b]")).toBe(0);
    expect(parseTimestampToSeconds("")).toBe(0);
  });
});

describe("secondsToTimestamp", () => {
  it("formats seconds as [MM:SS.ss]", () => {
    expect(secondsToTimestamp(0)).toBe("[00:00.00]");
    expect(secondsToTimestamp(5)).toBe("[00:05.00]");
    expect(secondsToTimestamp(62.5)).toBe("[01:02.50]");
    expect(secondsToTimestamp(6000)).toBe("[100:00.00]");
  });

  it("rounds to centiseconds", () => {
    expect(secondsToTimestamp(1.234)).toBe("[00:01.23]");
    expect(secondsToTimestamp(1.235)).toBe("[00:01.24]");
    expect(secondsToTimestamp(59.999)).toBe("[01:00.00]");
  });
});

describe("validateTimestampFormat", () => {
  it("accepts MM:SS.ss", () => {
    expect(validateTimestampFormat("00:00.00")).toBe(true);
    expect(validateTimestampFormat("99:59.99")).toBe(true);
  });

  it("rejects wrong shapes and out-of-range seconds", () => {
    expect(validateTimestampFormat("0:00.00")).toBe(false);
    expect(validateTimestampFormat("00:00.0")).toBe(false);
    expect(validateTimestampFormat("00:60.00")).toBe(false);
    expect(validateTimestampFormat("[00:00.00]")).toBe(false);
  });
});

describe("validateTimestampRange", () => {
  const timestamps = ["[00:10.00]", "[00:20.00]", "[--:--.--]", "[00:40.00]"];

  it("accepts a value between the surrounding timestamps", () => {
    expect(validateTimestampRange(1, 15, timestamps)).toEqual({
      valid: true,
      message: "",
    });
  });

  it("skips placeholders when looking for neighbours", () => {
    expect(validateTimestampRange(3, 30, timestamps).valid).toBe(true);
    expect(validateTimestampRange(1, 30, timestamps).valid).toBe(true);
    expect(validateTimestampRange(1, 40, timestamps).valid).toBe(false);
  });

  it("rejects a value at or before the previous timestamp", () => {
    expect(validateTimestampRange(1, 10, timestamps)).toMatchObject({
      valid: false,
      message: "Must be later than [00:10.00]",
    });
    expect(validateTimestampRange(1, 9, timestamps)).toMatchObject({
      valid: false,
      message: "Must be after [00:10.00]",
    });
  });

  it("rejects a value at or after the next timestamp", () => {
    expect(validateTimestampRange(2, 40, timestamps)).toMatchObject({
      valid: false,
      message: "Must be before [00:40.00]",
    });
  });

  it("allows the first line to start at 00:00.00", () => {
    expect(validateTimestampRange(0, 0, ["[--:--.--]", "[00:10.00]"])).toEqual({
      valid: true,
      message: "",
    });
  });

  it("rejects a later line that repeats the previous timestamp", () => {
    expect(validateTimestampRange(1, 10, timestamps)).toMatchObject({
      valid: false,
    });
  });
});

describe("formatTimeDisplay", () => {
  it("formats whole minutes and seconds", () => {
    expect(formatTimeDisplay(0)).toBe("00:00");
    expect(formatTimeDisplay(65.9)).toBe("1:05");
    expect(formatTimeDisplay(3600)).toBe("60:00");
  });

  it("falls back to 00:00 for missing or invalid values", () => {
    expect(formatTimeDisplay(undefined)).toBe("00:00");
    expect(formatTimeDisplay(Number.NaN)).toBe("00:00");
  });
});
