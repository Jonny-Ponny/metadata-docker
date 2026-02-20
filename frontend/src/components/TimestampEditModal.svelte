<!-- src/components/TimestampEditModal.svelte -->
<script>
  import {
    parseTimestampToSeconds,
    secondsToTimestamp,
    validateTimestampFormat,
    validateTimestampRange,
  } from "../utils/index.js";

  // Svelte 5: Use $props() instead of export let
  let {
    show = false,
    lineIndex = -1,
    currentValue = "",
    currentTime = 0,
    timestamps = [],
    USLT = "",
    onClose = () => {},
    onSave = (index, value) => {},
  } = $props();

  // Svelte 5: Use $state() for local reactive state
  let editingTimestampValue = $state("");
  let timestampError = $state("");

  function handleClose() {
    onClose();
  }

  function handleSave() {
    // First validate the format
    if (!validateTimestampFormat(editingTimestampValue)) {
      timestampError = "Invalid format. Use MM:SS.ss (e.g., 01:23.45)";
      return;
    }

    // Extra validation for seconds (should be 00-59)
    const parts = editingTimestampValue.split(/[:.]/);
    if (parts.length === 3) {
      const seconds = parseInt(parts[1]);
      if (seconds > 59) {
        timestampError = "Seconds cannot exceed 59";
        return;
      }
    }

    const newTimestamp = `[${editingTimestampValue}]`;
    const newTimestampSeconds = parseTimestampToSeconds(newTimestamp);

    // Validate timestamp is within allowed range
    const validation = validateTimestampRange(
      lineIndex,
      newTimestampSeconds,
      timestamps,
    );
    if (!validation.valid) {
      timestampError = validation.message;
      return;
    }

    onSave(lineIndex, editingTimestampValue);
  }

  function useCurrentTime() {
    const timestamp = secondsToTimestamp(currentTime);
    // Remove brackets and ensure proper format
    editingTimestampValue = timestamp.slice(1, -1);

    // Validate seconds don't exceed 59
    const parts = editingTimestampValue.split(/[:.]/);
    if (parts.length === 3) {
      let [minutes, seconds, centiseconds] = parts;
      if (parseInt(seconds) > 59) {
        seconds = "59";
        editingTimestampValue = `${minutes}:${seconds}.${centiseconds}`;
      }
    }
  }

  // Calculate allowed range for hints
  const allowedRange = $derived(
    (() => {
      const lines = USLT.split("\n");
      let prevSeconds = 0;
      for (let i = lineIndex - 1; i >= 0; i--) {
        if (timestamps[i] && timestamps[i] !== "[--:--.--]") {
          prevSeconds = parseTimestampToSeconds(timestamps[i]);
          break;
        }
      }

      let nextSeconds = Number.MAX_VALUE;
      for (let i = lineIndex + 1; i < timestamps.length; i++) {
        if (timestamps[i] && timestamps[i] !== "[--:--.--]") {
          nextSeconds = parseTimestampToSeconds(timestamps[i]);
          break;
        }
      }

      const prevTime = secondsToTimestamp(prevSeconds);
      const nextTime =
        nextSeconds !== Number.MAX_VALUE
          ? secondsToTimestamp(nextSeconds)
          : "end of song";

      return {
        prevTime,
        nextTime,
      };
    })(),
  );

  // Initialize when shown
  $effect(() => {
    if (show) {
      editingTimestampValue = currentValue;
      timestampError = "";

      // Add event listener to prevent keyboard events from bubbling
      const handleKeyDown = (e) => {
        // Stop propagation for all keyboard events when modal is open
        e.stopPropagation();
      };

      window.addEventListener("keydown", handleKeyDown, true); // Use capture phase

      return () => {
        window.removeEventListener("keydown", handleKeyDown, true);
      };
    }
  });

  // Input formatting
  // =======================
  // Add these functions to your script section
  function formatTimestampInput(value) {
    // Remove all non-digit characters
    const digits = value.replace(/\D/g, "");

    // Limit to 6 digits (MMSSss)
    const limited = digits.slice(0, 6);

    // Format as MM:SS.ss with proper padding
    if (limited.length === 0) return "";

    // Pad with zeros to ensure we have enough digits
    const padded = limited.padEnd(6, "0");

    // Extract parts
    let minutes = padded.slice(0, 2);
    let seconds = padded.slice(2, 4);
    let centiseconds = padded.slice(4, 6);

    // Validate seconds (max 59)
    if (parseInt(seconds) > 59) {
      seconds = "59";
    }

    // Build the formatted string based on how many digits we actually have
    if (limited.length <= 2) {
      // Only minutes entered so far
      return limited;
    } else if (limited.length <= 4) {
      // Minutes and partial seconds entered
      return `${limited.slice(0, 2)}:${limited.slice(2)}`;
    } else {
      // Full timestamp with all parts
      return `${minutes}:${seconds}.${centiseconds}`;
    }
  }

  function handleTimestampInput(e) {
    const input = e.target;
    const rawValue = input.value;
    const cursorPos = input.selectionStart;

    // Store the raw digit count before formatting
    const digitCountBefore = editingTimestampValue.replace(/\D/g, "").length;

    // Format the input
    const formatted = formatTimestampInput(rawValue);

    if (formatted !== editingTimestampValue) {
      editingTimestampValue = formatted;

      // Calculate new cursor position based on digit count
      const digitCountAfter = formatted.replace(/\D/g, "").length;
      const digitsTyped = digitCountAfter > digitCountBefore ? 1 : 0;

      if (cursorPos) {
        // Count digits up to cursor position
        const textBeforeCursor = rawValue.slice(0, cursorPos);
        const digitsBeforeCursor = textBeforeCursor.replace(/\D/g, "").length;

        // Calculate new position
        let newPos = digitsBeforeCursor;

        // Add separators based on how many digits we have
        if (digitsBeforeCursor > 2) newPos += 1; // Add for colon
        if (digitsBeforeCursor > 4) newPos += 1; // Add for period
        if (digitsBeforeCursor > 6) newPos = formatted.length; // End of string

        // Ensure we don't go beyond the formatted string
        newPos = Math.min(newPos, formatted.length);

        // Use setTimeout to set cursor after render
        setTimeout(() => {
          input.setSelectionRange(newPos, newPos);
        }, 0);
      }
    }
  }

  function handleTimestampKeydown(e) {
    // Stop propagation to prevent App from handling Delete key
    e.stopPropagation();

    if (e.key === "Enter") {
      e.preventDefault();
      handleSave();
    } else if (e.key === "Escape") {
      handleClose();
    }
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="modal-overlay" onclick={handleClose}>
    <div class="timestamp-editor" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>Edit Timestamp for Line {lineIndex + 1}</h3>
        <button title="Close" class="modal-close" onclick={handleClose}>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="timestamp-input-group">
          <!-- svelte-ignore a11y_autofocus -->
          <input
            type="text"
            bind:value={editingTimestampValue}
            placeholder="MM:SS.ss (e.g., 01:23.45)"
            class="timestamp-input"
            oninput={handleTimestampInput}
            onkeydown={handleTimestampKeydown}
            autofocus
          />
          <div class="timestamp-example">
            Format: MM:SS.ss (minutes:seconds.milliseconds)
          </div>

          {#if timestampError}
            <div class="timestamp-error">{timestampError}</div>
          {/if}

          <div class="timestamp-hints">
            <p><strong>Allowed range:</strong></p>
            <p>Between {allowedRange.prevTime} and {allowedRange.nextTime}</p>
            <p class="timestamp-current-time">
              <button class="btn btn-small" onclick={useCurrentTime}>
                Use Current Playback Time ({secondsToTimestamp(currentTime)})
              </button>
            </p>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick={handleClose}>
          Cancel
        </button>
        <button class="btn btn-primary" onclick={handleSave}>
          Save Timestamp
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(3px);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    animation: fadeIn 0.2s ease-out;
  }

  .timestamp-editor {
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    width: 100%;
    max-width: 500px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.3s ease-out;
  }

  .modal-header {
    padding: 20px 24px;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .modal-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #333;
  }

  .modal-close {
    background: none;
    border: none;
    padding: 4px;
    cursor: pointer;
    color: #666;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .modal-close:hover {
    color: #333;
    background-color: rgba(0, 0, 0, 0.05);
  }

  .modal-body {
    padding: 24px;
    flex: 1;
    overflow-y: auto;
  }

  .modal-footer {
    padding: 20px 24px;
    border-top: 1px solid #e0e0e0;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    flex-shrink: 0;
  }

  .timestamp-input-group {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .timestamp-input {
    padding: 12px 16px;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    font-family: monospace;
    font-size: 16px;
    text-align: center;
    transition: border-color 0.2s;
  }

  .timestamp-input:focus {
    outline: none;
    border-color: #fd7d05;
  }

  .timestamp-example {
    font-size: 13px;
    color: #666;
    text-align: center;
    font-family: monospace;
  }

  .timestamp-error {
    background-color: #ffebee;
    color: #c62828;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    text-align: center;
  }

  .timestamp-hints {
    background-color: #f8f9fa;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 13px;
    color: #666;
  }

  .timestamp-hints p {
    margin: 4px 0;
    line-height: 1.4;
  }

  .timestamp-current-time {
    margin-top: 8px;
    text-align: center;
  }

  /* Dark mode overrides */
  :global(body.dark) .timestamp-editor {
    background: #2d2d2d;
    color: #e0e0e0;
  }

  :global(body.dark) .modal-header {
    border-bottom-color: #444;
  }

  :global(body.dark) .modal-header h3 {
    color: #e0e0e0;
  }

  :global(body.dark) .modal-close {
    color: #b0b0b0;
  }

  :global(body.dark) .modal-close:hover {
    color: #e0e0e0;
    background-color: #3d3d3d;
  }

  :global(body.dark) .timestamp-input {
    background: #1e1e1e;
    border-color: #444;
    color: #e0e0e0;
  }

  :global(body.dark) .timestamp-input:focus {
    border-color: #ff9f4b;
  }

  :global(body.dark) .timestamp-example {
    color: #b0b0b0;
  }

  :global(body.dark) .timestamp-error {
    background-color: #442222;
    color: #ff9999;
  }

  :global(body.dark) .timestamp-hints {
    background: #3d3d3d;
    color: #b0b0b0;
  }

  :global(body.dark) .btn-secondary {
    background: #3d3d3d;
    color: #e0e0e0;
    border: 1px solid #444;
  }

  :global(body.dark) .btn-secondary:hover {
    background: #4d4d4d;
  }

  :global(body.dark) .btn-primary {
    background: #ff9f4b;
    color: #1e1e1e;
  }

  :global(body.dark) .btn-primary:hover {
    background: #ffb06f;
  }

  :global(body.dark) .btn-small {
    background-color: #3d3d3d;
    color: #e0e0e0;
    border-color: #555;
  }

  :global(body.dark) .btn-small:hover {
    background-color: #4d4d4d;
  }

  /* Button styles */
  .btn {
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    border: none;
  }

  .btn-primary {
    background-color: #fd7d05;
    color: white;
  }

  .btn-primary:hover {
    background-color: #ff5e00;
  }

  .btn-secondary {
    background-color: #f0f0f0;
    color: #666;
    border: 1px solid #ddd;
  }

  .btn-secondary:hover {
    background-color: #e0e0e0;
  }

  .btn-small {
    padding: 6px 12px;
    font-size: 12px;
    background-color: #f0f0f0;
    color: #666;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-small:hover {
    background-color: #e0e0e0;
  }

  /* Dark mode button styles */
  :global(body.dark) .btn-primary {
    background-color: #ff9f4b;
    color: #1e1e1e;
  }

  :global(body.dark) .btn-primary:hover {
    background-color: #ffb06f;
  }

  :global(body.dark) .btn-secondary {
    background-color: #3d3d3d;
    color: #e0e0e0;
    border-color: #555;
  }

  :global(body.dark) .btn-secondary:hover {
    background-color: #4d4d4d;
  }
</style>
