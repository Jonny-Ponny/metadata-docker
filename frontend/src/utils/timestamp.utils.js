// src/utils/timestamp.utils.js

/**
 * Convert timestamp string like [00:00.00] to seconds
 * @param {string} timestamp - Format: [MM:SS.ss]
 * @returns {number} Time in seconds
 */
export function parseTimestampToSeconds(timestamp) {
  // Remove brackets and split
  const timeStr = timestamp.slice(1, -1); // Remove [ and ]
  const parts = timeStr.split(":");

  if (parts.length !== 2) return 0;

  const minutes = parseInt(parts[0], 10) || 0;
  const seconds = parseFloat(parts[1]) || 0;

  return minutes * 60 + seconds;
}


/**
 * Convert seconds to timestamp string [MM:SS.ss]
 * @param {number} seconds - Time in seconds
 * @returns {string} Format: [MM:SS.ss]
 */
export function secondsToTimestamp(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  const minutesStr = minutes.toString().padStart(2, "0");
  const secondsStr = remainingSeconds.toFixed(2).padStart(5, "0");

  return `[${minutesStr}:${secondsStr}]`;
}

/**
 * Validate timestamp format (MM:SS.ss)
 * @param {string} timestamp - Without brackets, e.g. "00:00.00"
 * @returns {boolean} True if valid format
 */
export function validateTimestampFormat(timestamp) {
  const regex = /^\d{2}:\d{2}\.\d{2}$/;
  if (!regex.test(timestamp)) return false;

  const parts = timestamp.split(":");
  const minutes = parseInt(parts[0], 10);
  const seconds = parseFloat(parts[1]);

  return minutes >= 0 && seconds >= 0 && seconds < 60;
}


/**
 * Validate timestamp is within allowed range (between previous and next timestamps)
 * @param {number} lineIndex - Index of the line being edited
 * @param {number} newSeconds - New timestamp in seconds
 * @param {Array<string>} timestamps - All timestamps array
 * @returns {Object} { valid: boolean, message: string }
 */
export function validateTimestampRange(lineIndex, newSeconds, timestamps) {
  const result = { valid: true, message: "" };

  // Find previous valid timestamp
  let prevSeconds = 0;
  for (let i = lineIndex - 1; i >= 0; i--) {
    if (timestamps[i] !== "[--:--.--]") {
      prevSeconds = parseTimestampToSeconds(timestamps[i]);
      break;
    }
  }

  // Find next valid timestamp
  let nextSeconds = Number.MAX_VALUE;
  for (let i = lineIndex + 1; i < timestamps.length; i++) {
    if (timestamps[i] !== "[--:--.--]") {
      nextSeconds = parseTimestampToSeconds(timestamps[i]);
      break;
    }
  }

  // Validate against previous timestamp
  if (newSeconds < prevSeconds) {
    result.valid = false;
    result.message = `Must be after ${secondsToTimestamp(prevSeconds)}`;
    return result;
  }

  // Validate against next timestamp (if there is one)
  if (nextSeconds !== Number.MAX_VALUE && newSeconds >= nextSeconds) {
    result.valid = false;
    result.message = `Must be before ${secondsToTimestamp(nextSeconds)}`;
    return result;
  }

  // Special case: allow equal to previous if it's the first line with content
  if (newSeconds === prevSeconds && lineIndex > 0) {
    result.valid = false;
    result.message = `Must be later than ${secondsToTimestamp(prevSeconds)}`;
    return result;
  }

  return result;
}



/**
 * Format time for display (MM:SS)
 * @param {number} seconds - Time in seconds
 * @returns {string} Formatted time string
 */
export function formatTimeDisplay(seconds) {
  if (!seconds || isNaN(seconds)) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}