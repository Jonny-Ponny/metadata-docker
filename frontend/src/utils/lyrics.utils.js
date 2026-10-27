// @ts-check
// src/utils/lyrics.utils.js

import {
  parseTimestampToSeconds,
  secondsToTimestamp,
} from "./timestamp.utils.js";

export const TIMESTAMP_PLACEHOLDER = "[--:--.--]";

// Standard LRC metadata tags. Any other bracketed line is treated as lyrics.
const ID_TAG_KEYS = new Set([
  "ti",
  "ar",
  "al",
  "by",
  "re",
  "ve",
  "length",
  "offset",
  "tool",
  "encoding",
  "au",
]);

const ID_TAG_REGEX = /^\[([a-zA-Z]+):(.*)\]$/;

// A timestamp may use 1-3 minute digits and 1-3 decimals with "." or ",".
const LEADING_TIMESTAMP_REGEX = /^\s*\[(\d{1,3}):(\d{1,2}(?:[.,]\d{1,3})?)\]/;

/**
 * Remove a leading LRC timestamp from a line.
 * @param {string} value - Raw line (or remaining part of a line)
 * @returns {{ seconds: number, rest: string } | null}
 */
function takeLeadingTimestamp(value) {
  const match = value.match(LEADING_TIMESTAMP_REGEX);
  if (!match) return null;

  const minutes = parseInt(match[1], 10) || 0;
  const seconds = parseFloat(match[2].replace(",", ".")) || 0;

  return {
    seconds: minutes * 60 + seconds,
    rest: value.slice(match[0].length),
  };
}

/**
 * Parse LRC (or plain) lyrics into editable lines and timestamps.
 *
 * Handles BOM/CRLF, ID tags, comma decimals, 1-3 decimal digits and lines
 * with multiple timestamps (expanded into one entry per timestamp).
 *
 * @param {string | null} text - Raw lyrics text
 * @returns {{
 *   text: string,
 *   timestamps: string[],
 *   headers: Object<string, string>,
 *   hasOffset: boolean
 * }}
 */
export function parseLrc(text) {
  const lines = [];
  const timestamps = [];
  /** @type {Record<string, string>} */
  const headers = {};
  let hasOffset = false;

  const source = String(text ?? "")
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/);

  for (const rawLine of source) {
    const trimmed = rawLine.trim();

    if (trimmed === "") {
      lines.push("");
      timestamps.push(TIMESTAMP_PLACEHOLDER);
      continue;
    }

    const idMatch = trimmed.match(ID_TAG_REGEX);
    if (idMatch && ID_TAG_KEYS.has(idMatch[1].toLowerCase())) {
      const key = idMatch[1].toLowerCase();
      headers[key] = idMatch[2].trim();
      if (key === "offset") hasOffset = true;
      continue;
    }

    const foundTimestamps = [];
    let rest = rawLine;
    let hadPlaceholder = false;

    // Strip our own "[--:--.--]" marker when re-importing a copy
    const placeholderMatch = rest.match(/^\s*\[--:--\.--\]/);
    if (placeholderMatch) {
      hadPlaceholder = true;
      rest = rest.slice(placeholderMatch[0].length);
    }

    let next = takeLeadingTimestamp(rest);
    while (next) {
      foundTimestamps.push(next.seconds);
      rest = next.rest;
      next = takeLeadingTimestamp(rest);
    }

    if (foundTimestamps.length === 0) {
      // Not a timed line - keep it verbatim (preserves indentation)
      lines.push(hadPlaceholder ? rest.trim() : rawLine);
      timestamps.push(TIMESTAMP_PLACEHOLDER);
      continue;
    }

    const lyric = rest.trim();
    for (const seconds of foundTimestamps) {
      lines.push(lyric);
      timestamps.push(secondsToTimestamp(seconds));
    }
  }

  return {
    text: lines.join("\n"),
    timestamps,
    headers,
    hasOffset,
  };
}

/**
 * Process edited text to extract timestamps and clean lyrics
 * @param {string} text - Raw lyrics text with optional timestamps
 * @returns {{ text: string, timestamps: string[] }}
 */
export function processEditedLyrics(text) {
  const { text: processedText, timestamps } = parseLrc(text);
  return { text: processedText, timestamps };
}

/**
 * Shift every real timestamp by an offset.
 *
 * Works in centiseconds to avoid floating point drift. Placeholders are left
 * untouched and a shift that would move a timestamp before 00:00.00 is
 * rejected so the result always stays valid LRC.
 *
 * @param {string[]} timestamps - Timestamp strings (may contain placeholders)
 * @param {number} offsetSeconds - Offset to apply, negative shifts earlier
 * @returns {{
 *   ok: boolean,
 *   timestamps: string[],
 *   count: number,
 *   error: string
 * }}
 */
export function shiftTimestamps(timestamps, offsetSeconds) {
  const offset = Number(offsetSeconds);
  if (!Number.isFinite(offset)) {
    return {
      ok: false,
      timestamps: [...timestamps],
      count: 0,
      error: "Invalid shift amount",
    };
  }

  const delta = Math.round(offset * 100);

  let minCentiseconds = Infinity;
  let count = 0;
  for (const timestamp of timestamps) {
    if (!timestamp || timestamp === TIMESTAMP_PLACEHOLDER) continue;
    const centiseconds = Math.round(parseTimestampToSeconds(timestamp) * 100);
    minCentiseconds = Math.min(minCentiseconds, centiseconds);
    count++;
  }

  if (count === 0 || delta === 0) {
    return { ok: true, timestamps: [...timestamps], count, error: "" };
  }

  if (minCentiseconds + delta < 0) {
    const maxEarlier = (minCentiseconds / 100).toFixed(2);
    return {
      ok: false,
      timestamps: [...timestamps],
      count,
      error: `Cannot shift earlier than 00:00.00 (max -${maxEarlier}s)`,
    };
  }

  return {
    ok: true,
    count,
    error: "",
    timestamps: timestamps.map((timestamp) => {
      if (!timestamp || timestamp === TIMESTAMP_PLACEHOLDER) return timestamp;
      const centiseconds =
        Math.round(parseTimestampToSeconds(timestamp) * 100) + delta;
      return secondsToTimestamp(centiseconds / 100);
    }),
  };
}

/**
 * Build an LRC string from editable lyrics and timestamps.
 *
 * Untimed lines are written as plain text (never as "[--:--.--]") and empty
 * header values are omitted.
 *
 * @param {string[]} lines - Lyric lines
 * @param {string[]} timestamps - Timestamps matching the lines
 * @param {Record<string, string | undefined>} headers
 * @returns {string}
 */
export function buildLrc(lines, timestamps = [], headers = {}) {
  const headerLines = [];
  const headerTags = [
    ["ti", "title"],
    ["ar", "artist"],
    ["al", "album"],
  ];

  for (const [tag, key] of headerTags) {
    const value = String(headers[key] ?? "")
      .replace(/[\r\n]+/g, " ")
      .trim();
    if (value) headerLines.push(`[${tag}:${value}]`);
  }

  const body = lines.map((line, index) => {
    const text = line ?? "";
    const timestamp = timestamps[index];

    if (!timestamp || timestamp === TIMESTAMP_PLACEHOLDER) return text;
    return text === "" ? timestamp : `${timestamp} ${text}`;
  });

  return [...headerLines, ...body].join("\n");
}
