<!-- src/components/LRCEditor.svelte -->
<script>
  import { onMount } from "svelte";
  import {
    parseTimestampToSeconds,
    secondsToTimestamp,
    validateTimestampRange,
    processEditedLyrics,
    parseLrc,
    shiftTimestamps,
    buildLrc,
    downloadTextFile,
    findActiveLine,
    isRealTimestamp,
    TIMESTAMP_PLACEHOLDER,
    toast,
    keepFocusInDialog,
    keepTabInDialog,
    dialogOpenEffect,
  } from "../utils/index.js";

  // Import the old modals
  import TimestampEditModal from "./TimestampEditModal.svelte";
  import EditModal from "./EditModal.svelte";

  /**
   * @typedef {Object} TrackInfo
   * @property {string} [title]
   * @property {string} [artist]
   * @property {string} [album]
   */

  /**
   * @typedef {Object} Props
   * @property {boolean} [isOpen]
   * @property {() => void} [onClose]
   * @property {string | null} [filePath]
   * @property {string} [initialLyrics]
   * @property {string[]} [initialTimestamps]
   * @property {TrackInfo} [trackInfo]
   * @property {(payload: { lyrics: string, timestamps: string[], synchronizedLyrics: string | null, hasTimestamps: boolean }) => void} [onSave]
   */

  // Props
  /** @type {Props} */
  let {
    isOpen = false,
    onClose = () => {},
    filePath = null,
    initialLyrics = "",
    initialTimestamps = [],
    trackInfo = {},
    onSave = () => {},
  } = $props();

  // ========== STATE VARIABLES ==========
  let USLT = $state("");
  let timestamps = $state(/** @type {string[]} */ ([]));
  let synchronizedLyricsText = $state("");
  let currentActiveLine = $state(-1);

  let currentPlaybackTime = $state(0);

  // Bulk timestamp tools
  let shiftAmount = $state(/** @type {number | string} */ (0.5));
  let lrcFileInput = $state(/** @type {HTMLInputElement | null} */ (null));

  // For the old timestamp edit modal
  let showTimestampModal = $state(false);

  // The dialog panel, so the shared helpers can read it from the event.
  let panel = $state(/** @type {HTMLDivElement | null} */ (null));
  let editingTimestampIndex = $state(-1);
  let editingTimestampValue = $state("");

  // For the old edit modal
  let showEditModal = $state(false);
  let editingText = $state("");

  // Track if we've initialized
  let hasInitialized = $state(false);

  // ========== INITIALIZATION ==========
  function initializeFromLyrics() {
    let newUSLT = "";
    /** @type {string[]} */
    let newTimestamps = [];

    if (initialLyrics && initialLyrics.trim() !== "") {
      // If we have timestamps, use them directly
      if (initialTimestamps && initialTimestamps.length > 0) {
        newUSLT = initialLyrics;
        newTimestamps = [...initialTimestamps];
      } else {
        // Otherwise parse from the lyrics text
        const result = processEditedLyrics(initialLyrics);
        newUSLT = result.text;
        newTimestamps = result.timestamps;
      }
    }

    // Ensure timestamps array matches number of lines
    const lineCount = newUSLT.split("\n").length;
    if (newTimestamps.length > lineCount) {
      newTimestamps = newTimestamps.slice(0, lineCount);
    }
    while (newTimestamps.length < lineCount) {
      newTimestamps.push(TIMESTAMP_PLACEHOLDER);
    }

    // Only update if different
    if (
      newUSLT !== USLT ||
      JSON.stringify(newTimestamps) !== JSON.stringify(timestamps)
    ) {
      USLT = newUSLT;
      timestamps = newTimestamps;
      updateSynchronizedLyricsText();
    }
  }

  // Call when modal opens - only once
  $effect(() => {
    if (isOpen && !hasInitialized) {
      initializeFromLyrics();
      hasInitialized = true;
    }

    // Reset when modal closes
    if (!isOpen) {
      hasInitialized = false;
    }
  });

  // ========== FUNCTIONS ==========
  /** The lyric lines, split once instead of once per render pass. */
  const lines = $derived(USLT.split("\n"));

  /**
   * @param {number} index
   * @returns {boolean}
   */
  function isTimed(index) {
    return isRealTimestamp(timestamps[index]);
  }

  /**
   * Trim the timestamp list back to the current line count. Bulk operations
   * (import, clearing, shifting) keep every entry, so placeholders can pile up
   * when the text is shortened; the extra entries would shift a line index and
   * the highlight would point at the wrong row.
   */
  function alignTimestamps() {
    const lineCount = lines.length;
    if (timestamps.length > lineCount) {
      timestamps = timestamps.slice(0, lineCount);
    }
    while (timestamps.length < lineCount) {
      timestamps.push(TIMESTAMP_PLACEHOLDER);
    }
  }

  function updateSynchronizedLyricsText() {
    // Untimed lines are written as plain text so the result is valid LRC
    synchronizedLyricsText = buildLrc(lines, timestamps);
  }

  /**
   * @param {number} lineIndex
   */
  function handleLineClick(lineIndex) {
    if (!isTimed(lineIndex)) return;
    const targetTime = parseTimestampToSeconds(timestamps[lineIndex]);

    // Dispatch event for player to seek
    const event = new CustomEvent("lyrics-seek", {
      detail: { time: targetTime },
    });
    window.dispatchEvent(event);
  }

  /**
   * @param {number} currentTime
   */
  function updateActiveLine(currentTime) {
    if (timestamps.length === 0) {
      currentActiveLine = -1;
      return;
    }

    const activeLineIndex = findActiveLine(timestamps, currentTime);

    if (activeLineIndex !== currentActiveLine) {
      currentActiveLine = activeLineIndex;
      if (currentActiveLine !== -1) {
        requestAnimationFrame(() => scrollToCurrentLine());
      }
    }
  }

  function scrollToCurrentLine() {
    if (currentActiveLine === -1) return;

    const activeLine = document.querySelector(
      `[data-line-index="${currentActiveLine}"]`,
    );
    if (activeLine) {
      activeLine.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  /**
   * Keep a line in view while its timestamp is applied, so the line the user
   * is syncing does not drift off-centre between captures.
   * @param {Element | null} line
   */
  function scrollToLine(line) {
    if (line) {
      line.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  // ========== TIMESTAMP EDITING USING OLD MODAL ==========
  /**
   * @param {number} lineIndex
   */
  function openTimestampEditor(lineIndex) {
    const currentTimestamp = timestamps[lineIndex];
    if (currentTimestamp === "[--:--.--]") {
      // Get current playback time from player
      const event = new CustomEvent("get-current-time", {
        detail: {
          callback: (/** @type {number} */ time) => {
            editingTimestampValue = secondsToTimestamp(time).slice(1, -1);
          },
        },
      });
      window.dispatchEvent(event);
    } else {
      editingTimestampValue = currentTimestamp.slice(1, -1);
    }
    editingTimestampIndex = lineIndex;
    showTimestampModal = true;
  }

  function closeTimestampModal() {
    showTimestampModal = false;
    editingTimestampIndex = -1;
    editingTimestampValue = "";
  }

  /**
   * @param {number} index
   * @param {string} value
   */
  function saveTimestampFromModal(index, value) {
    const newTimestamp = `[${value}]`;
    const newTimestampSeconds = parseTimestampToSeconds(newTimestamp);
    const validation = validateTimestampRange(
      index,
      newTimestampSeconds,
      timestamps,
    );

    if (!validation.valid) {
      // Show error via toast since the modal has its own validation
      toast.error(validation.message);
      return;
    }

    timestamps[index] = newTimestamp;
    updateSynchronizedLyricsText();
    closeTimestampModal();

    if (currentActiveLine === index) updateActiveLine(0);
  }

  // ========== EDIT MODAL FUNCTIONS ==========
  function openEditModal() {
    editingText = USLT;
    showEditModal = true;
  }

  function closeEditModal() {
    showEditModal = false;
    editingText = "";
  }

  async function saveEditedText() {
    if (editingText !== USLT) {
      const result = processEditedLyrics(editingText);
      USLT = result.text;
      timestamps = result.timestamps;
      alignTimestamps();

      updateSynchronizedLyricsText();
      currentActiveLine = -1;
    }
    closeEditModal();
  }

  // Insert current time to next line
  function insertCurrentTimeToNextLine() {
    if (USLT === "") return;

    const event = new CustomEvent("get-current-time", {
      detail: {
        callback: (/** @type {number} */ time) => {
          alignTimestamps();
          const lineCount = lines.length;
          if (lineCount === 0) return;

          let targetIndex;
          if (currentActiveLine === -1) {
            targetIndex = 0;
          } else {
            targetIndex = currentActiveLine + 1;
          }
          if (targetIndex >= lineCount) return;

          // Store the target element for scrolling
          const targetElement = document.querySelector(
            `[data-line-index="${targetIndex}"]`,
          );

          // Update the timestamp
          timestamps[targetIndex] = secondsToTimestamp(time);
          if (timestamps.length < lines.length) {
            while (timestamps.length < lines.length)
              timestamps.push("[--:--.--]");
          }

          // Update the synchronized LRC text and move the highlight with it
          updateSynchronizedLyricsText();
          currentActiveLine = targetIndex;

          // Keep the new line in view while the heights re-equalise
          scrollToLine(targetElement);
        },
      },
    });
    window.dispatchEvent(event);
  }

  // Copy synchronized lyrics
  async function copySynchronizedLyrics() {
    const textToCopy = buildLrc(lines, timestamps);

    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(textToCopy);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = textToCopy;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      toast.success("Lyrics copied to clipboard");
    } catch (err) {
      console.error("Failed to copy text: ", err);
      toast.error(
        `Failed to copy text: ${
          err instanceof Error ? err.message : String(err)
        }`,
      );
    }
  }

  // ========== SAVE HANDLER ==========
  function handleSave() {
    // At least one real timestamp means this is LRC content. Untimed lines
    // are written as plain lines by updateSynchronizedLyricsText().
    const hasTimestamps = timestamps.some(isRealTimestamp);

    onSave({
      lyrics: USLT,
      timestamps,
      // Only ship the LRC string when there is something to sync
      synchronizedLyrics: hasTimestamps ? synchronizedLyricsText : null,
      hasTimestamps,
    });
    onClose();
  }

  /**
   * @param {Event} e
   */
  function stopPropagation(e) {
    e.stopPropagation();
  }

  function clearAllTimestamps() {
    if (timestamps.length === 0) return;

    timestamps = timestamps.map(() => "[--:--.--]");
    updateSynchronizedLyricsText();
    currentActiveLine = -1;
    toast.success("All timestamps cleared");
  }

  // ========== BULK TIMESTAMP TOOLS ==========
  function refreshAfterBulkEdit({ resetActive = true } = {}) {
    updateSynchronizedLyricsText();

    if (resetActive) {
      currentActiveLine = -1;
    } else {
      updateActiveLine(currentPlaybackTime);
    }
  }

  /**
   * @param {number} direction
   */
  function applyTimestampShift(direction) {
    const amount = Math.abs(Number(shiftAmount));
    if (!Number.isFinite(amount) || amount === 0) {
      toast.info("Enter a non-zero shift amount");
      return;
    }

    const delta = Math.abs(amount) * (direction < 0 ? -1 : 1);
    const result = shiftTimestamps(timestamps, delta);

    if (!result.ok) {
      toast.error(result.error);
      return;
    }
    if (result.count === 0) {
      toast.info("No timestamps to shift");
      return;
    }

    timestamps = result.timestamps;
    refreshAfterBulkEdit({ resetActive: false });

    const label = `${delta > 0 ? "+" : ""}${delta.toFixed(2)}s`;
    toast.success(
      `Shifted ${result.count} timestamp${
        result.count === 1 ? "" : "s"
      } by ${label}`,
    );
  }

  function handleImportClick() {
    lrcFileInput?.click();
  }

  /**
   * @param {Event} event
   */
  function handleShiftAmountInput(event) {
    const target = /** @type {HTMLInputElement} */ (event.target);
    const raw = target.value;
    // Keep digits and a single decimal separator, normalise "," to "."
    const [whole, ...decimals] = raw
      .replace(/,/g, ".")
      .replace(/[^0-9.]/g, "")
      .split(".");
    const cleaned =
      decimals.length > 0 ? `${whole}.${decimals.join("")}` : whole;

    if (target.value !== cleaned) {
      target.value = cleaned;
    }
    shiftAmount = cleaned;
  }

  function clampShiftAmount() {
    const value = Math.abs(Number(shiftAmount));
    shiftAmount = Number.isFinite(value) ? value : 0;
  }

  /**
   * @param {Event} event
   */
  async function handleLrcFileSelected(event) {
    const target = /** @type {HTMLInputElement} */ (event.target);
    const file = target.files?.[0];
    // Reset so selecting the same file again still fires onchange
    target.value = "";
    if (!file) return;

    try {
      const parsed = parseLrc(await file.text());

      if (!parsed.text.trim()) {
        toast.info("No lyrics found in the selected file");
        return;
      }

      USLT = parsed.text;
      timestamps = parsed.timestamps;
      alignTimestamps();

      refreshAfterBulkEdit();
      toast.success(`Imported lyrics from ${file.name}`);

      if (parsed.hasOffset) {
        toast.info(
          "[offset] tags are ignored - use the Shift controls to adjust timing",
        );
      }
    } catch (err) {
      console.error("Failed to import LRC file:", err);
      toast.error(
        `Import failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }

  function buildExportFilename() {
    const title = (trackInfo?.title || "").trim();
    const artist = (trackInfo?.artist || "").trim();
    const fallback = filePath
      ? (filePath.split(/[\\/]/).pop() ?? filePath).replace(/\.[^.]+$/, "")
      : "lyrics";

    const base = title ? (artist ? `${artist} - ${title}` : title) : fallback;
    const safe = base.replace(/[\\/:*?"<>|]/g, "_").trim() || "lyrics";

    return `${safe}.lrc`;
  }

  function exportLrcFile() {
    if (!USLT.trim()) {
      toast.info("No lyrics to export");
      return;
    }

    const content = buildLrc(lines, timestamps, {
      title: trackInfo?.title,
      artist: trackInfo?.artist,
      album: trackInfo?.album,
    });

    downloadTextFile(buildExportFilename(), content);
    toast.success("LRC file downloaded");
  }

  async function copyUnsyncedText() {
    const textToCopy = USLT;

    if (!textToCopy || textToCopy.trim() === "") {
      toast.info("No unsynced lyrics to copy");
      return;
    }

    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(textToCopy);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = textToCopy;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      toast.success("Unsynced lyrics copied to clipboard");
    } catch (err) {
      console.error("Failed to copy text: ", err);
      toast.error(
        `Failed to copy: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }

  // Key binds
  /**
   * @param {KeyboardEvent} e
   */
  function handleKeydown(e) {
    // Escape is handled by `dialogOpenEffect` above, so it closes the editor
    // only when nothing was opened on top of it.
    if (e.key === "Escape") return;

    // Ignore if focus is inside an input/textarea or content-editable
    const target = /** @type {HTMLElement} */ (e.target);
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable
    ) {
      return;
    }

    const key = e.key.toLowerCase();
    if (key === "s") {
      e.preventDefault();
      insertCurrentTimeToNextLine();
    } else if (key === "c") {
      e.preventDefault();
      insertCurrentTimeToCurrentLine();
    }
  }

  function insertCurrentTimeToCurrentLine() {
    const targetIndex = currentActiveLine;
    if (targetIndex === -1 || targetIndex >= timestamps.length) {
      toast.info("No active line to set timestamp");
      return;
    }
    if (USLT === "") return;

    // Keep the line being synced in view while the heights re-equalise
    const targetElement = document.querySelector(
      `[data-line-index="${targetIndex}"]`,
    );

    // Read the live playback position via the player. The stored
    // timeupdate value can be up to one event interval stale, which
    // would write timestamps slightly early.
    const event = new CustomEvent("get-current-time", {
      detail: {
        callback: (/** @type {number} */ time) => {
          if (time === undefined || time === null) {
            toast.error("Current playback time not available");
            return;
          }

          const newTimestamp = secondsToTimestamp(time);
          alignTimestamps();
          timestamps[targetIndex] = newTimestamp;

          updateSynchronizedLyricsText();
          scrollToLine(targetElement);
        },
      },
    });
    window.dispatchEvent(event);
  }

  // Escape closes the editor only while it is the topmost dialog; the other
  // shortcuts are handled by `handleKeydown` below.
  $effect(() => dialogOpenEffect(panel, isOpen, onClose));

  $effect(() => {
    if (!isOpen) return;
    document.addEventListener("keydown", handleKeydown);
    return () => {
      document.removeEventListener("keydown", handleKeydown);
    };
  });

  // Listen for player time updates - using the existing player events
  onMount(() => {
    /**
     * @param {Event} e
     */
    const handleTimeUpdate = (e) => {
      const { time } = /** @type {CustomEvent<{ time: number }>} */ (e).detail;
      currentPlaybackTime = time; // Store the current timeF
      updateActiveLine(time);
    };

    window.addEventListener("player-time-update", handleTimeUpdate);

    return () => {
      window.removeEventListener("player-time-update", handleTimeUpdate);
    };
  });
</script>

{#if isOpen}
  <!-- Modal Overlay -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="lyrics-modal-overlay"
    onclick={(e) => {
      e.stopPropagation();
      onClose();
    }}
  >
    <!-- Make the entire modal scrollable -->
    <div
      class="lyrics-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Synced lyrics editor"
      tabindex="-1"
      data-player-space="true"
      bind:this={panel}
      onkeydown={keepTabInDialog}
      onfocusin={keepFocusInDialog}
      onclick={stopPropagation}
    >
      <input
        class="hidden-file-input"
        type="file"
        accept=".lrc,.txt,text/plain"
        bind:this={lrcFileInput}
        onchange={handleLrcFileSelected}
      />
      <!-- Header - stays fixed -->
      <div class="modal-header">
        <h2>Synced Lyrics Editor</h2>
        <div class="header-actions">
          <!-- Edit Lyrics button -->
          <button
            class="header-btn"
            onclick={openEditModal}
            title="Edit lyrics"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
              />
              <path
                d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
              />
            </svg>
            <span>Edit</span>
          </button>

          <!-- Import .lrc button -->
          <button
            class="header-btn"
            onclick={handleImportClick}
            title="Import lyrics from an .lrc file"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 3v12" />
              <path d="m7 8 5-5 5 5" />
              <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
            </svg>
            <span>Import .lrc</span>
          </button>

          <!-- Export .lrc button -->
          <button
            class="header-btn"
            onclick={exportLrcFile}
            title="Download synchronized lyrics as an .lrc file"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 3v12" />
              <path d="m7 10 5 5 5-5" />
              <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
            </svg>
            <span>Export .lrc</span>
          </button>

          <!-- Copy LRC button (with timestamps) -->
          <button
            class="header-btn"
            onclick={copySynchronizedLyrics}
            title="Copy LRC format with timestamps"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path
                d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
              />
            </svg>
            <span>Copy LRC</span>
          </button>

          <!-- Copy Text button (unsynced only) -->
          <button
            class="header-btn"
            onclick={copyUnsyncedText}
            title="Copy lyrics without timestamps"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path
                d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
              />
            </svg>
            <span>Copy Text</span>
          </button>

          <!-- Clear Timestamps button -->
          <button
            class="header-btn clear-timestamps"
            onclick={clearAllTimestamps}
            title="Clear all timestamps"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
              />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
            <span>Clear</span>
          </button>

          <button
            class="close-btn"
            onclick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            title="Close"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M15 5L5 15M5 5L15 15"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>
      </div>

      <!-- Scrollable content area -->
      <!-- tabindex="-1": Firefox adds scrollable regions to the tab order, so Tab
             would land on this pane instead of its first control. -->
      <div class="modal-scrollable-content" tabindex="-1">
        <!-- One row per lyric line: its timestamp and its text stay aligned
             because they are cells of the same grid row, so the columns never
             need to be re-measured or re-equalised. -->
        <div class="lyric-table-wrapper">
          <div class="lyric-table" role="table" aria-label="Lyrics">
            <div class="lyric-table-header" role="row">
              <div class="column-header timestamp-header" role="columnheader">
                Timestamps
              </div>
              <div class="column-header lyrics-header" role="columnheader">
                Lyrics
              </div>
            </div>

            {#each lines as line, index (index)}
              <div
                class="lyric-row {index === currentActiveLine ? 'playing' : ''}"
                role="row"
                data-line-index={index}
              >
                <div class="timestamp-cell" role="cell">
                  <button
                    class="timestamp-jump"
                    id="modal-timestamp-{index}"
                    onclick={() => handleLineClick(index)}
                    disabled={!isTimed(index)}
                    title={isTimed(index)
                      ? `Jump to ${timestamps[index]}`
                      : "No timestamp available"}
                  >
                    <span class="timestamp-value">
                      {timestamps[index] || TIMESTAMP_PLACEHOLDER}
                    </span>
                  </button>
                  <button
                    class="timestamp-edit-btn"
                    onclick={() => openTimestampEditor(index)}
                    title="Edit timestamp"
                    aria-label="Edit timestamp for line {index + 1}"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path
                        d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
                      />
                      <path
                        d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
                      />
                    </svg>
                  </button>
                </div>
                <div class="lyric-cell" id="modal-line-{index}" role="cell">
                  <!-- Untimed lines have nothing to seek to, so they stay plain
                       text; a timed line is a button like its timestamp. -->
                  {#if isTimed(index)}
                    <button
                      class="lyric-jump"
                      onclick={() => handleLineClick(index)}
                      title="Jump to {timestamps[index]}"
                    >
                      {#if line === ""}<span class="empty-line-placeholder"
                          >empty line</span
                        >{:else}{line}{/if}
                    </button>
                  {:else if line === ""}
                    <span class="empty-line-placeholder">empty line</span>
                  {:else}
                    {line}
                  {/if}
                </div>
              </div>
            {:else}
              <div class="empty-state">No lyrics loaded</div>
            {/each}
          </div>
        </div>
      </div>

      <!-- Footer with Save and Cancel - stays fixed -->
      <div class="modal-footer">
        <div class="footer-left">
          <div class="shift-control">
            <span class="shift-label">Shift</span>
            <button
              class="shift-btn"
              onclick={() => applyTimestampShift(-1)}
              disabled={USLT === ""}
              title="Shift all timestamps earlier"
              aria-label="Shift all timestamps earlier"
            >
              −
            </button>
            <input
              class="shift-input"
              type="text"
              inputmode="decimal"
              value={shiftAmount}
              oninput={handleShiftAmountInput}
              onblur={clampShiftAmount}
              aria-label="Shift amount in seconds"
              title="Shift amount in seconds"
            />
            <span class="shift-unit">s</span>
            <button
              class="shift-btn"
              onclick={() => applyTimestampShift(1)}
              disabled={USLT === ""}
              title="Shift all timestamps later"
              aria-label="Shift all timestamps later"
            >
              +
            </button>
          </div>
        </div>

        <div class="footer-center">
          <button
            class="insert-time-btn"
            onclick={insertCurrentTimeToNextLine}
            disabled={USLT === ""}
            title="Insert current playback time to next line"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>Synchronize line</span>
          </button>
        </div>

        <div class="footer-right">
          <button
            class="btn btn-secondary"
            onclick={(e) => {
              e.stopPropagation();
              onClose();
            }}>Cancel</button
          >
          <button class="btn btn-primary" onclick={handleSave}
            >Save to File</button
          >
        </div>
      </div>
    </div>
  </div>

  <!-- Old Timestamp Edit Modal -->
  <TimestampEditModal
    show={showTimestampModal}
    lineIndex={editingTimestampIndex}
    currentValue={editingTimestampValue}
    {timestamps}
    onClose={closeTimestampModal}
    onSave={saveTimestampFromModal}
  />

  <!-- Old Edit Modal -->
  <EditModal
    show={showEditModal}
    bind:editingText
    onClose={closeEditModal}
    onSave={saveEditedText}
  />
{/if}

<style>
  /* Import old styles as reference */
  .lyrics-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    animation: fadeIn 0.2s ease;
    padding-bottom: 70px;
    pointer-events: auto;
  }

  .lyrics-modal {
    background: white;
    border-radius: 8px;
    width: 90vw;
    height: 85vh;
    display: flex;
    flex-direction: column;
    animation: scaleIn 0.2s ease;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    pointer-events: auto;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 2px solid #ddd;
    background-color: #f0f0f0;
    flex-shrink: 0;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 18px;
    color: #333;
    font-weight: 600;
  }

  .close-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    color: #666;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .close-btn:hover {
    color: var(--color-primary);
    background-color: var(--color-primary-transparent);
    transform: scale(1.1);
  }

  .close-btn svg {
    width: 20px;
    height: 20px;
    display: block;
  }

  /* Scrollable content area */
  .modal-scrollable-content {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 20px 0;
  }

  /* Wrapper to add padding around the table */
  .lyric-table-wrapper {
    padding: 0 20px;
  }

  /* Two columns: the timestamp gutter and the lyrics. The lyric column takes
     all the width left over, so the text sits in the middle of the screen. */
  .lyric-table {
    display: grid;
    grid-template-columns: minmax(150px, 18%) 1fr;
    width: 100%;
    border: 2px solid #ddd;
    border-radius: 4px;
    overflow: hidden;
    background-color: white;
  }

  .lyric-table-header,
  .lyric-row {
    display: grid;
    grid-template-columns: subgrid;
    grid-column: 1 / -1;
  }

  .column-header {
    padding: 15px;
    border-bottom: 2px solid #ddd;
    background-color: #f0f0f0;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    font-weight: 600;
    color: #333;
    line-height: 1.2;
    box-sizing: border-box;
  }

  .lyric-table-header {
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .timestamp-header {
    border-right: 2px solid #ddd;
  }

  .timestamp-cell {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    padding: 0 8px;
    border-right: 2px solid #ddd;
    border-bottom: 1px solid #eee;
    background-color: #f8f9fa;
    font-family: monospace;
    min-height: 44px;
    box-sizing: border-box;
  }

  .timestamp-jump {
    flex: 1;
    min-width: 0;
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: #666;
    text-align: right;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
  }

  .timestamp-jump:hover:not(:disabled) {
    color: var(--color-primary);
    text-decoration: underline;
  }

  .timestamp-jump:disabled {
    cursor: default;
    color: #999;
  }

  .lyric-cell {
    display: flex;
    align-items: center;
    justify-content: center;
    border-bottom: 1px solid #eee;
    font-size: 14px;
    line-height: 1.4;
    text-align: center;
    word-wrap: break-word;
    overflow-wrap: break-word;
    min-height: 44px;
    box-sizing: border-box;
    transition: background-color 0.2s;
  }

  .lyric-jump {
    display: block;
    width: 100%;
    padding: 10px 16px;
    background: none;
    border: none;
    font: inherit;
    color: inherit;
    text-align: center;
    cursor: pointer;
  }

  .lyric-jump:hover {
    text-decoration: underline;
    text-decoration-color: #bbb;
  }

  .lyric-row:hover .lyric-cell,
  .lyric-row:hover .timestamp-cell {
    background-color: #f5f5f5;
  }

  .lyric-row.playing .lyric-cell {
    color: var(--color-primary);
    font-weight: 600;
    background-color: var(--color-lrc-playing-transparent);
  }

  .lyric-row.playing .timestamp-cell,
  .lyric-row.playing .timestamp-jump {
    color: var(--color-primary);
    font-weight: 600;
  }

  .lyric-row.playing .timestamp-cell {
    background-color: var(--color-lrc-playing-transparent);
  }

  .timestamp-value {
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .timestamp-edit-btn {
    background: none;
    border: none;
    padding: 2px;
    cursor: pointer;
    color: #666;
    border-radius: 3px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: all 0.2s;
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  .lyric-row:hover .timestamp-edit-btn,
  .timestamp-edit-btn:focus-visible {
    opacity: 1;
  }

  .timestamp-edit-btn:hover {
    color: var(--color-primary);
    background-color: var(--color-primary-transparent);
  }

  .timestamp-edit-btn svg {
    width: 12px;
    height: 12px;
    display: block;
  }

  .empty-state {
    text-align: center;
    color: #999;
    font-style: italic;
    padding: 20px;
    font-size: 14px;
    line-height: 1.5;
  }

  .empty-line-placeholder {
    opacity: 0.5;
    font-style: italic;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .header-btn {
    background: transparent;
    border: 1px solid #ddd;
    color: #666;
    padding: 6px 12px;
    height: 32px;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    transition: all 0.2s;
  }

  .header-btn svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .header-btn span {
    white-space: nowrap;
  }

  .header-btn:hover {
    background: var(--color-primary-transparent);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  .header-btn.clear-timestamps {
    border-color: #ff4444;
    color: #ff4444;
  }

  .header-btn.clear-timestamps:hover {
    background: rgba(255, 68, 68, 0.1);
  }

  .insert-time-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    background-color: var(--color-primary);
    color: white;
    padding: 10px 20px;
    border-radius: 6px;
    border: none;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
  }

  .insert-time-btn:hover:not(:disabled) {
    background-color: var(--color-primary-focus);
    transform: translateY(-1px);
  }

  .insert-time-btn:disabled {
    background-color: #cccccc;
    cursor: not-allowed;
    opacity: 0.6;
  }

  .insert-time-btn svg {
    stroke: white;
  }

  .hidden-file-input {
    display: none;
  }

  .shift-control {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .shift-label,
  .shift-unit {
    font-size: 13px;
    color: #666;
  }

  .shift-input {
    width: 68px;
    height: 32px;
    padding: 0 6px;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: white;
    color: #333;
    font-size: 13px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .shift-input:focus {
    outline: none;
    border-color: var(--color-primary);
  }

  .shift-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: transparent;
    color: #666;
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    transition: all 0.2s;
  }

  .shift-btn:hover:not(:disabled) {
    background: var(--color-primary-transparent);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  .shift-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .modal-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-top: 2px solid #ddd;
    background-color: #f0f0f0;
    flex-shrink: 0;
  }

  .footer-left,
  .footer-right {
    flex: 1;
    display: flex;
    gap: 12px;
  }

  .footer-left {
    justify-content: flex-start;
  }

  .footer-right {
    justify-content: flex-end;
  }

  .footer-center {
    display: flex;
    justify-content: center;
  }

  /* Button styles */
  .btn {
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
  }

  .btn-primary {
    background-color: var(--color-primary);
    color: white;
  }

  .btn-primary:hover {
    background-color: var(--color-primary-focus);
    transform: translateY(-1px);
  }

  .btn-secondary {
    background-color: #f0f0f0;
    color: #666;
  }

  .btn-secondary:hover {
    background-color: #e0e0e0;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @keyframes scaleIn {
    from {
      transform: scale(0.95);
    }
    to {
      transform: scale(1);
    }
  }

  /* Dark mode */
  :global(body.dark) .lyrics-modal {
    background: #2d2d2d;
  }

  :global(body.dark) .modal-header {
    background-color: #3d3d3d;
    border-bottom-color: #444;
  }

  :global(body.dark) .modal-header h2 {
    color: #e0e0e0;
  }

  :global(body.dark) .close-btn {
    color: #b0b0b0;
  }

  :global(body.dark) .close-btn:hover {
    color: var(--color-primary-dark);
    background-color: var(--color-primary-transparent-dark);
  }

  :global(body.dark) .lyric-table {
    border-color: #444;
    background-color: #1e1e1e;
  }

  :global(body.dark) .column-header {
    background-color: #3d3d3d;
    border-bottom-color: #444;
    color: #e0e0e0;
  }

  :global(body.dark) .timestamp-header {
    border-right-color: var(--color-primary-dark);
  }

  :global(body.dark) .timestamp-cell {
    background-color: #2d2d2d;
    border-right-color: var(--color-primary-dark);
    border-bottom-color: #444;
  }

  :global(body.dark) .timestamp-jump {
    color: #b0b0b0;
  }

  :global(body.dark) .timestamp-jump:disabled {
    color: #808080;
  }

  :global(body.dark) .lyric-cell {
    border-bottom-color: #444;
    color: #e0e0e0;
  }

  :global(body.dark) .lyric-row:hover .lyric-cell,
  :global(body.dark) .lyric-row:hover .timestamp-cell {
    background-color: #3d3d3d;
  }

  :global(body.dark) .lyric-row.playing .timestamp-jump {
    color: var(--color-primary-dark);
  }

  :global(body.dark) .timestamp-edit-btn {
    color: #b0b0b0;
  }

  :global(body.dark) .timestamp-edit-btn:hover {
    color: var(--color-primary-dark);
    background-color: var(--color-primary-transparent-dark);
  }

  :global(body.dark) .empty-state {
    color: #808080;
  }

  :global(body.dark) .insert-time-btn {
    background-color: var(--color-primary-dark);
    color: #1e1e1e;
  }

  :global(body.dark) .insert-time-btn:hover:not(:disabled) {
    background-color: var(--color-primary-dark-focus);
  }

  :global(body.dark) .insert-time-btn:disabled {
    background-color: #444;
    color: #808080;
  }

  :global(body.dark) .modal-footer {
    background-color: #3d3d3d;
    border-top-color: #444;
  }

  :global(body.dark) .btn-secondary {
    background-color: #3d3d3d;
    color: #e0e0e0;
    border: 1px solid #444;
  }

  :global(body.dark) .btn-secondary:hover {
    background-color: #4d4d4d;
  }

  :global(body.dark) .btn-primary {
    background-color: var(--color-primary-dark);
    color: #1e1e1e;
  }

  :global(body.dark) .btn-primary:hover {
    background-color: var(--color-primary-dark-focus);
  }

  :global(body.dark) .shift-label,
  :global(body.dark) .shift-unit {
    color: #b0b0b0;
  }

  :global(body.dark) .shift-input {
    background: #2d2d2d;
    border-color: #555;
    color: #e0e0e0;
  }

  :global(body.dark) .shift-input:focus {
    border-color: var(--color-primary-dark);
  }

  :global(body.dark) .shift-btn {
    border-color: #555;
    color: #aaa;
  }

  :global(body.dark) .shift-btn:hover:not(:disabled) {
    background: var(--color-primary-transparent-dark);
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }

  :global(.player) {
    z-index: 10001 !important;
    pointer-events: auto !important;
  }

  :global(body.dark) .insert-time-btn:disabled svg {
    stroke: #808080;
  }

  :global(body.dark) .header-btn {
    border-color: #555;
    color: #aaa;
  }

  :global(body.dark) .header-btn:hover {
    background: var(--color-primary-transparent-dark);
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .header-btn.clear-timestamps {
    border-color: #ff6b6b;
    color: #ff6b6b;
  }

  :global(body.dark) .header-btn.clear-timestamps:hover {
    background: rgba(255, 107, 107, 0.2);
  }
</style>
