// src/utils/lyrics.utils.js

import {
  parseTimestampToSeconds,
  secondsToTimestamp,
} from "./timestamp.utils.js";

export const TIMESTAMP_PLACEHOLDER = "[--:--.--]";

/**
 * Whether a timestamp entry is a real, parseable timestamp.
 *
 * Blank lines and untimed lines are stored as a placeholder so the lyrics and
 * timestamps arrays stay aligned; those entries must be skipped by anything
 * that reasons about playback timing.
 * @param {string | null | undefined} timestamp
 * @returns {boolean}
 */
export function isRealTimestamp(timestamp) {
  return (
    typeof timestamp === "string" &&
    timestamp !== "" &&
    timestamp !== TIMESTAMP_PLACEHOLDER
  );
}

/**
 * Find the lyric line that should be highlighted at a playback position.
 *
 * This is the last timed line at or before `currentTime`, ignoring untimed
 * lines. Untimed lines sit between timed ones (a blank line in the middle of
 * an LRC file, for example), so the next timed line cannot be assumed to be
 * the immediate neighbour; taking the placeholder as the end of the previous
 * line's interval used to pin the highlight to that line forever.
 *
 * @param {string[]} timestamps - Timestamp strings (may contain placeholders)
 * @param {number} currentTime - Playback position in seconds
 * @returns {number} Index of the active line, or -1 before the first timestamp
 */
export function findActiveLine(timestamps, currentTime) {
  let activeLine = -1;
  let activeSeconds = Number.NEGATIVE_INFINITY;

  for (let i = 0; i < timestamps.length; i++) {
    if (!isRealTimestamp(timestamps[i])) continue;

    const seconds = parseTimestampToSeconds(timestamps[i]);
    // `>=` keeps the last line when several lines share a timestamp, which is
    // how LRC repeats a chorus line at several times.
    if (seconds <= currentTime && seconds >= activeSeconds) {
      activeLine = i;
      activeSeconds = seconds;
    }
  }

  return activeLine;
}

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
 * Shift only the timestamps at the given line indices.
 *
 * Used for editing one part of a song (a second verse that is off by a second)
 * or a single line, while the rest of the file keeps its timing. The moved
 * timestamps must stay after the nearest unmoved timestamp before them and
 * before the nearest unmoved timestamp after them, otherwise the LRC would no
 * longer read top to bottom in time order.
 *
 * Works in centiseconds like `shiftTimestamps` so repeated shifts do not
 * accumulate floating point drift.
 *
 * @param {string[]} timestamps - Timestamp strings (may contain placeholders)
 * @param {number} offsetSeconds - Offset to apply, negative shifts earlier
 * @param {Set<number> | number[]} indices - Line indices allowed to move
 * @returns {{
 *   ok: boolean,
 *   timestamps: string[],
 *   count: number,
 *   error: string
 * }}
 */
export function shiftTimestampSelection(timestamps, offsetSeconds, indices) {
  const offset = Number(offsetSeconds);
  if (!Number.isFinite(offset)) {
    return {
      ok: false,
      timestamps: [...timestamps],
      count: 0,
      error: "Invalid shift amount",
    };
  }

  const selected =
    indices instanceof Set ? indices : new Set(indices.map(Number));
  const delta = Math.round(offset * 100);

  const movable = [];
  for (let i = 0; i < timestamps.length; i++) {
    if (selected.has(i) && isRealTimestamp(timestamps[i])) movable.push(i);
  }

  if (movable.length === 0 || delta === 0) {
    return { ok: true, timestamps: [...timestamps], count: 0, error: "" };
  }

  const toCentiseconds = (/** @type {string} */ value) =>
    Math.round(parseTimestampToSeconds(value) * 100);

  // The closest unmoved timed line on each side of the selection bounds it.
  const nearestUnselected = (
    /** @type {number} */ from,
    /** @type {1 | -1} */ step,
  ) => {
    for (let i = from + step; i >= 0 && i < timestamps.length; i += step) {
      if (!isRealTimestamp(timestamps[i])) continue;
      return selected.has(i) ? null : toCentiseconds(timestamps[i]);
    }
    return null;
  };

  for (const index of movable) {
    const moved = toCentiseconds(timestamps[index]) + delta;

    if (moved < 0) {
      const maxEarlier = (toCentiseconds(timestamps[index]) / 100).toFixed(2);
      return {
        ok: false,
        timestamps: [...timestamps],
        count: movable.length,
        error: `Cannot shift line ${index + 1} earlier than 00:00.00 (max -${maxEarlier}s)`,
      };
    }

    const previous = nearestUnselected(index, -1);
    if (previous !== null && moved < previous) {
      const label = secondsToTimestamp(previous / 100);
      return {
        ok: false,
        timestamps: [...timestamps],
        count: movable.length,
        error: `Line ${index + 1} would move before ${label} on the line above`,
      };
    }

    const next = nearestUnselected(index, 1);
    if (next !== null && moved > next) {
      const label = secondsToTimestamp(next / 100);
      return {
        ok: false,
        timestamps: [...timestamps],
        count: movable.length,
        error: `Line ${index + 1} would move after ${label} on the line below`,
      };
    }
  }

  const shifted = [...timestamps];
  for (const index of movable) {
    shifted[index] = secondsToTimestamp(
      (toCentiseconds(timestamps[index]) + delta) / 100,
    );
  }

  return { ok: true, timestamps: shifted, count: movable.length, error: "" };
}

/**
 * Insert an empty, untimed line into the lyrics.
 *
 * `afterIndex` is the line it goes below; -1 puts it at the very top. The
 * timestamp for the new line is a placeholder, so it stays untimed until the
 * user captures or types one.
 *
 * @param {string} text - Lyrics as stored (lines joined by "\n")
 * @param {string[]} timestamps - Timestamps matching the lines
 * @param {number} afterIndex - Index of the line above the new one
 * @returns {{ text: string, timestamps: string[], index: number }}
 */
export function insertLyricLine(text, timestamps, afterIndex) {
  const lines = String(text ?? "").split("\n");
  const at = Math.min(Math.max(afterIndex + 1, 0), lines.length);
  lines.splice(at, 0, "");

  const nextTimestamps = [...timestamps];
  nextTimestamps.splice(at, 0, TIMESTAMP_PLACEHOLDER);

  return {
    text: lines.join("\n"),
    timestamps: nextTimestamps,
    index: at,
  };
}

/**
 * Remove lines and their timestamps.
 *
 * The lyrics are never emptied: deleting everything leaves a single empty
 * line, which is what an editor opens with for a file that has no lyrics.
 *
 * @param {string} text - Lyrics as stored (lines joined by "\n")
 * @param {string[]} timestamps - Timestamps matching the lines
 * @param {Set<number> | number[]} indices - Line indices to remove
 * @returns {{ text: string, timestamps: string[], removed: number, index: number }}
 *   `index` is the line that now sits where the first removed line was, or -1
 *   when there is nothing to place a cursor on.
 */
export function deleteLyricLines(text, timestamps, indices) {
  const lines = String(text ?? "").split("\n");
  const selected =
    indices instanceof Set ? indices : new Set(indices.map(Number));
  const removedIndices = lines
    .map((_line, index) => index)
    .filter((index) => selected.has(index));

  if (removedIndices.length === 0) {
    return {
      text: lines.join("\n"),
      timestamps: [...timestamps],
      removed: 0,
      index: -1,
    };
  }

  const kept = lines.filter((_line, index) => !selected.has(index));
  const keptTimestamps = timestamps.filter(
    (_ts, index) => !selected.has(index),
  );

  const first = removedIndices[0];
  return {
    text: kept.length > 0 ? kept.join("\n") : "",
    timestamps:
      kept.length > 0
        ? keptTimestamps.slice(0, kept.length)
        : [TIMESTAMP_PLACEHOLDER],
    removed: removedIndices.length,
    index: kept.length > 0 ? Math.min(first, kept.length - 1) : -1,
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
