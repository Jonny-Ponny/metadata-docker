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