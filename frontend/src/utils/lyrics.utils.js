// src/utils/lyrics.utils.js

/**
 * Process edited text to extract timestamps and clean lyrics
 * @param {string} text - Raw lyrics text with optional timestamps
 * @returns {Object} { text: string, timestamps: string[] }
 */
export function processEditedLyrics(text) {
  const lines = text.split("\n");
  const processedLines = [];
  const extractedTimestamps = [];

  for (let i = 0; i < lines.length; i++) {
    const originalLine = lines[i];
    const trimmedLine = originalLine.trim();

    // Check if it's an empty line or a line with only whitespace
    if (trimmedLine === "") {
      // Empty line - preserve it as empty
      processedLines.push("");
      extractedTimestamps.push("[--:--.--]");
      continue;
    }

    // Check if trimmed line starts with timestamp pattern [00:00.00] or [00:00.000]
    if (trimmedLine.startsWith("[") && trimmedLine.includes("]")) {
      const timestampEnd = trimmedLine.indexOf("]");

      // Check if it's a valid timestamp format with 2 or 3 decimal places
      if (timestampEnd > 0 && timestampEnd <= trimmedLine.length - 1) {
        // Extract the timestamp (up to the closing bracket)
        const timestamp = trimmedLine.substring(0, timestampEnd + 1);

        // Check if it looks like a valid timestamp [00:00.00] or [00:00.000]
        // This regex matches both 2 and 3 decimal places: \d{2}:\d{2}\.\d{2,3}
        if (timestamp.match(/^\[\d{2}:\d{2}\.\d{2,3}\]$/)) {
          // It's a valid timestamp - extract text after it
          extractedTimestamps.push(timestamp);
          
          // Extract text after the closing bracket
          const afterBracket = trimmedLine.substring(timestampEnd + 1).trim();
          
          // Check if there's actual text after the timestamp
          if (afterBracket) {
            processedLines.push(afterBracket);
          } else {
            processedLines.push(""); // Empty line after timestamp
          }
        } else {
          // Not a valid timestamp format - keep the ENTIRE original line
          processedLines.push(originalLine);
          extractedTimestamps.push("[--:--.--]");
        }
      } else {
        // Not a valid timestamp format - keep the ENTIRE original line
        processedLines.push(originalLine);
        extractedTimestamps.push("[--:--.--]");
      }
    } else {
      // Not a timestamp line, keep the original line (preserves indentation/formatting)
      processedLines.push(originalLine);
      extractedTimestamps.push("[--:--.--]");
    }
  }

  return {
    text: processedLines.join("\n"),
    timestamps: extractedTimestamps,
  };
}