<!-- src/components/LRCEditor.svelte -->
<script>
    import { onMount, tick } from "svelte";
    import {
        parseTimestampToSeconds,
        secondsToTimestamp,
        validateTimestampRange,
        processEditedLyrics,
        debounce,
        toast,
        equalizeElementHeights,
    } from "../utils/index.js";

    // Import the old modals
    import TimestampEditModal from "./TimestampEditModal.svelte";
    import EditModal from "./EditModal.svelte";

    // Props
    let {
        isOpen = false,
        onClose = () => {},
        filePath = null,
        initialLyrics = "",
        initialTimestamps = [],
        onSave = () => {},
    } = $props();

    // ========== STATE VARIABLES ==========
    let USLT = $state("");
    let timestamps = $state([]);
    let synchronizedLyricsText = $state("");
    let currentActiveLine = $state(-1);

    let currentPlaybackTime = $state(0);

    // For the old timestamp edit modal
    let showTimestampModal = $state(false);
    let editingTimestampIndex = $state(-1);
    let editingTimestampValue = $state("");

    // For the old edit modal
    let showEditModal = $state(false);
    let editingText = $state("");

    // Track if we've initialized
    let hasInitialized = $state(false);

    // Track line heights for equalization
    let lineHeights = new Map();
    let resizeObservers = new Map();

    // ========== INITIALIZATION ==========
    function initializeFromLyrics() {
        let newUSLT = "";
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
        if (newTimestamps.length < lineCount) {
            while (newTimestamps.length < lineCount) {
                newTimestamps.push("[--:--.--]");
            }
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

            // Setup height equalization after DOM update
            tick().then(() => {
                requestAnimationFrame(() => {
                    equalizeAllLineHeights();
                    setupResizeObservers();
                });
            });
        }

        // Reset when modal closes
        if (!isOpen) {
            hasInitialized = false;
            cleanupResizeObservers();
        }
    });

    // ========== FUNCTIONS ==========
    function updateSynchronizedLyricsText() {
        const lines = USLT.split("\n");
        const syncedLines = lines.map((line, i) => {
            const ts = timestamps[i] || "[--:--.--]";
            return `${ts} ${line}`;
        });
        synchronizedLyricsText = syncedLines.join("\n");
    }

    function handleLineClick(lineIndex) {
        const timestamp = timestamps[lineIndex];
        if (timestamp === "[--:--.--]") return;
        const targetTime = parseTimestampToSeconds(timestamp);

        // Dispatch event for player to seek
        const event = new CustomEvent("lyrics-seek", {
            detail: { time: targetTime },
        });
        window.dispatchEvent(event);
    }

    function updateActiveLine(currentTime) {
        if (timestamps.length === 0) {
            currentActiveLine = -1;
            return;
        }

        let activeLineIndex = -1;

        for (let i = 0; i < timestamps.length; i++) {
            const timestamp = timestamps[i];
            if (timestamp === "[--:--.--]") continue;
            const timestampSeconds = parseTimestampToSeconds(timestamp);

            if (i === timestamps.length - 1) {
                if (currentTime >= timestampSeconds) activeLineIndex = i;
            } else {
                const nextTimestamp = timestamps[i + 1];
                let nextTimestampSeconds = Number.MAX_VALUE;
                if (nextTimestamp !== "[--:--.--]") {
                    nextTimestampSeconds =
                        parseTimestampToSeconds(nextTimestamp);
                }
                if (
                    currentTime >= timestampSeconds &&
                    currentTime < nextTimestampSeconds
                ) {
                    activeLineIndex = i;
                    break;
                }
            }
        }

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

    // ========== HEIGHT EQUALISATION ==========
    function cleanupResizeObservers() {
        resizeObservers.forEach((observer) => observer.disconnect());
        resizeObservers.clear();
        lineHeights.clear();
    }

    function setupResizeObservers() {
        const lines = USLT.split("\n");
        if (lines.length === 0) return;

        const debouncedEqualizeLineHeight = debounce((lineIndex) => {
            equalizeLineHeight(lineIndex);
        }, 50);

        for (let i = 0; i < lines.length; i++) {
            const timestampLine = document.getElementById(
                `modal-timestamp-${i}`,
            );
            const lyricLine = document.getElementById(`modal-line-${i}`);
            const syncedLine = document.getElementById(`modal-synced-${i}`);

            [timestampLine, lyricLine, syncedLine].forEach((line, colIndex) => {
                if (line) {
                    const observer = new ResizeObserver(() => {
                        debouncedEqualizeLineHeight(i);
                    });
                    observer.observe(line);
                    resizeObservers.set(`${i}-${colIndex}`, observer);
                }
            });
        }
    }

    function equalizeLineHeight(lineIndex) {
        const lines = [
            document.getElementById(`modal-timestamp-${lineIndex}`),
            document.getElementById(`modal-line-${lineIndex}`),
            document.getElementById(`modal-synced-${lineIndex}`),
        ];
        const maxHeight = equalizeElementHeights(lines);
        if (maxHeight > 0) {
            const storedHeight = lineHeights.get(lineIndex) || 0;
            if (Math.abs(maxHeight - storedHeight) > 1) {
                lineHeights.set(lineIndex, maxHeight);
            }
        }
    }

    function equalizeAllLineHeights() {
        const lines = USLT.split("\n");
        if (lines.length === 0) return;

        for (let i = 0; i < lines.length; i++) {
            const linesToReset = [
                document.getElementById(`modal-timestamp-${i}`),
                document.getElementById(`modal-line-${i}`),
                document.getElementById(`modal-synced-${i}`),
            ].filter(Boolean);

            linesToReset.forEach((line) => {
                line.style.minHeight = "";
                line.style.height = "";
            });
        }

        requestAnimationFrame(() => {
            for (let i = 0; i < lines.length; i++) equalizeLineHeight(i);
        });
    }

    // ========== TIMESTAMP EDITING USING OLD MODAL ==========
    function openTimestampEditor(lineIndex) {
        const currentTimestamp = timestamps[lineIndex];
        if (currentTimestamp === "[--:--.--]") {
            // Get current playback time from player
            const event = new CustomEvent("get-current-time", {
                detail: {
                    callback: (time) => {
                        editingTimestampValue = secondsToTimestamp(time).slice(
                            1,
                            -1,
                        );
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

        // Re-equalize heights after timestamp change
        requestAnimationFrame(() => {
            equalizeAllLineHeights();
        });
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

            const lineCount = USLT.split("\n").length;
            if (timestamps.length < lineCount) {
                while (timestamps.length < lineCount) {
                    timestamps.push("[--:--.--]");
                }
            }

            updateSynchronizedLyricsText();
            currentActiveLine = -1;
        }
        closeEditModal();

        // Re-equalize heights after edit
        cleanupResizeObservers();
        await tick();
        requestAnimationFrame(() => {
            equalizeAllLineHeights();
            setupResizeObservers();
        });
    }

    // Insert current time to next line
    function insertCurrentTimeToNextLine() {
        if (USLT === "") return;

        const event = new CustomEvent("get-current-time", {
            detail: {
                callback: (time) => {
                    const lines = USLT.split("\n");
                    if (lines.length === 0) return;

                    let targetIndex;
                    if (currentActiveLine === -1) {
                        targetIndex = 0;
                    } else {
                        targetIndex = currentActiveLine + 1;
                    }
                    if (targetIndex >= lines.length) return;

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

                    // Update text but don't trigger re-equalize yet
                    updateSynchronizedLyricsText();
                    currentActiveLine = targetIndex;

                    // First scroll to the element BEFORE height equalization
                    if (targetElement) {
                        targetElement.scrollIntoView({
                            behavior: "smooth",
                            block: "center",
                        });
                    }

                    // Then handle height equalization after scroll starts
                    requestAnimationFrame(() => {
                        // Temporarily disable transitions during height equalization
                        const style = document.createElement("style");
                        style.id = "temp-no-transition";
                        style.textContent = `
                        .lyric-line {
                            transition: none !important;
                        }
                    `;
                        document.head.appendChild(style);

                        // Force a small delay to let scroll start
                        setTimeout(() => {
                            equalizeAllLineHeights();

                            // Remove the temp style after equalization
                            setTimeout(() => {
                                const tempStyle =
                                    document.getElementById(
                                        "temp-no-transition",
                                    );
                                if (tempStyle) tempStyle.remove();
                            }, 100);
                        }, 10);
                    });
                },
            },
        });
        window.dispatchEvent(event);
    }

    // Copy synchronized lyrics
    async function copySynchronizedLyrics() {
        const lines = USLT.split("\n");
        const syncedLines = lines.map((line, i) => {
            const ts = timestamps[i] || "[--:--.--]";
            return `${ts} ${line}`;
        });
        const textToCopy = syncedLines.join("\n");

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
            toast.error(`Failed to copy text: ${err.message}`);
        }
    }

    // ========== SAVE HANDLER ==========
    function handleSave() {
        onSave({
            lyrics: USLT,
            timestamps: timestamps,
            synchronizedLyrics: synchronizedLyricsText,
        });
        onClose();
    }

    function stopPropagation(e) {
        e.stopPropagation();
    }

    function clearAllTimestamps() {
        if (timestamps.length === 0) return;

        timestamps = timestamps.map(() => "[--:--.--]");
        updateSynchronizedLyricsText();
        currentActiveLine = -1;
        toast.success("All timestamps cleared");

        // Re-equalize heights
        requestAnimationFrame(() => {
            equalizeAllLineHeights();
        });
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
            toast.error(`Failed to copy: ${err.message}`);
        }
    }

    // Listen for player time updates - using the existing player events
    onMount(() => {
        const handleTimeUpdate = (e) => {
            const time = e.detail.time;
            currentPlaybackTime = time; // Store the current timeF
            updateActiveLine(e.detail.time);
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
        <div class="lyrics-modal" onclick={stopPropagation}>
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
                            <rect
                                x="9"
                                y="9"
                                width="13"
                                height="13"
                                rx="2"
                                ry="2"
                            />
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
                            <rect
                                x="9"
                                y="9"
                                width="13"
                                height="13"
                                rx="2"
                                ry="2"
                            />
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
                        <svg
                            width="20"
                            height="20"
                            viewBox="0 0 20 20"
                            fill="none"
                        >
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
            <div class="modal-scrollable-content">
                <!-- Three-Column Layout - Connected columns with proper padding -->
                <div class="space-parts-wrapper">
                    <div class="space-parts">
                        <!-- Timestamps Column -->
                        <div class="space-part left-part">
                            <div class="column-header">
                                <div class="header-content">
                                    <h3>Timestamps</h3>
                                </div>
                            </div>
                            <div class="column-content">
                                {#each USLT.split("\n") as line, index}
                                    <div
                                        class="lyric-line timestamp-line {index ===
                                        currentActiveLine
                                            ? 'playing'
                                            : ''}"
                                        id="modal-timestamp-{index}"
                                        data-line-index={index}
                                        onclick={() => handleLineClick(index)}
                                        style="cursor: {timestamps[index] &&
                                        timestamps[index] !== '[--:--.--]'
                                            ? 'pointer'
                                            : 'default'}"
                                        title={timestamps[index] &&
                                        timestamps[index] !== "[--:--.--]"
                                            ? "Click to jump to " +
                                              timestamps[index]
                                            : "No timestamp available"}
                                    >
                                        <div class="timestamp-container">
                                            <span class="timestamp-value">
                                                {timestamps[index] ||
                                                    "[--:--.--]"}
                                            </span>
                                            <button
                                                class="timestamp-edit-btn"
                                                onclick={(e) => {
                                                    e.stopPropagation(); // Prevent seeking when clicking edit button
                                                    openTimestampEditor(index);
                                                }}
                                                title="Edit timestamp"
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
                                    </div>
                                {:else}
                                    <div class="empty-state">
                                        No timestamps loaded
                                    </div>
                                {/each}
                            </div>
                        </div>

                        <!-- Unsynchronized Lyrics Column -->
                        <div class="space-part middle-part">
                            <div class="column-header">
                                <div class="header-content">
                                    <h3>Unsynchronized lyrics</h3>
                                </div>
                            </div>
                            <div class="column-content">
                                {#each USLT.split("\n") as line, index}
                                    <div
                                        class="lyric-line {index ===
                                        currentActiveLine
                                            ? 'playing'
                                            : ''}"
                                        id="modal-line-{index}"
                                        data-line-index={index}
                                        onclick={() => handleLineClick(index)}
                                        style="cursor: {timestamps[index] &&
                                        timestamps[index] !== '[--:--.--]'
                                            ? 'pointer'
                                            : 'default'}"
                                        title={timestamps[index] &&
                                        timestamps[index] !== "[--:--.--]"
                                            ? "Click to jump to " +
                                              timestamps[index]
                                            : "No timestamp available"}
                                    >
                                        {#if line === ""}
                                            <span class="empty-line-placeholder"
                                                >&nbsp;</span
                                            >
                                        {:else}
                                            {line}
                                        {/if}
                                    </div>
                                {:else}
                                    <div class="empty-state">
                                        No lyrics loaded
                                    </div>
                                {/each}
                            </div>
                        </div>

                        <!-- Synchronized Lyrics Column -->
                        <div class="space-part right-part">
                            <div class="column-header">
                                <div class="header-content">
                                    <h3>Synchronized lyrics</h3>
                                </div>
                            </div>
                            <div class="column-content">
                                {#each USLT.split("\n") as line, index}
                                    <div
                                        class="lyric-line synced-line {index ===
                                        currentActiveLine
                                            ? 'playing'
                                            : ''}"
                                        id="modal-synced-{index}"
                                        data-line-index={index}
                                        onclick={() => handleLineClick(index)}
                                        style="cursor: {timestamps[index] &&
                                        timestamps[index] !== '[--:--.--]'
                                            ? 'pointer'
                                            : 'default'}"
                                        title={timestamps[index] &&
                                        timestamps[index] !== "[--:--.--]"
                                            ? "Click to jump to " +
                                              timestamps[index]
                                            : "No timestamp available"}
                                    >
                                        {#if timestamps[index] && timestamps[index] !== "[--:--.--]"}
                                            {timestamps[index]}
                                            {#if line === ""}<span
                                                    class="empty-line-placeholder"
                                                    >&nbsp;</span
                                                >{:else}{line}{/if}
                                        {:else}
                                            [--:--.--] {#if line === ""}<span
                                                    class="empty-line-placeholder"
                                                    >&nbsp;</span
                                                >{:else}{line}{/if}
                                        {/if}
                                    </div>
                                {:else}
                                    <div class="empty-state">
                                        No synchronized lyrics loaded
                                    </div>
                                {/each}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Footer with Save and Cancel - stays fixed -->
            <div class="modal-footer">
                <div class="footer-left">
                    <!-- Empty div to balance the layout -->
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
        currentTime={currentPlaybackTime}
        {timestamps}
        {USLT}
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
        color: #fd7d05;
        background-color: rgba(253, 125, 5, 0.1);
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

    /* Wrapper to add padding around the columns */
    .space-parts-wrapper {
        padding: 0 20px;
    }

    /* Three columns layout - connected */
    .space-parts {
        display: flex;
        width: 100%;
        border: 2px solid #ddd;
        border-radius: 4px;
        overflow: hidden;
        background-color: white;
    }

    .space-part {
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }

    .left-part {
        width: 30%;
        min-width: 30%;
        border-right: 2px solid #ddd;
        background-color: #f8f9fa;
    }

    .middle-part {
        width: 40%;
        min-width: 40%;
        border-right: 2px solid #ddd;
        background-color: #ffffff;
    }

    .right-part {
        width: 30%;
        min-width: 30%;
        background-color: #f8f9fa;
    }

    .column-header {
        padding: 15px;
        border-bottom: 2px solid #ddd;
        background-color: #f0f0f0;
        flex-shrink: 0;
        height: 60px;
        display: flex;
        align-items: center;
    }

    .header-content {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 100%;
        gap: 8px;
        position: relative;
    }

    .column-header h3 {
        margin: 0;
        color: #333;
        font-size: 16px;
        font-weight: 600;
        line-height: 1.2;
    }

    .column-content {
        flex: 1;
        overflow: visible; /* Allow content to determine height */
        padding: 0;
    }

    /* Lyric line styles */
    .lyric-line {
        padding: 10px 12px;
        margin: 0;
        border-bottom: 1px solid #eee;
        cursor: pointer;
        min-height: 44px;
        display: flex;
        align-items: center;
        font-size: 14px;
        line-height: 1.4;
        transition: background-color 0.2s;
        box-sizing: border-box;
        word-wrap: break-word;
        overflow-wrap: break-word;
        width: 100%;
    }

    .lyric-line:hover {
        background-color: #f5f5f5;
    }

    .lyric-line.playing {
        color: #fd7d05 !important;
        font-weight: 600 !important;
        background-color: rgba(253, 125, 5, 0.05) !important;
    }

    .timestamp-line {
        font-family: monospace;
        color: #666;
        justify-content: center;
        text-align: center;
        background-color: #f8f9fa;
    }

    .timestamp-line.playing {
        color: #fd7d05 !important;
        font-weight: 600 !important;
        background-color: rgba(253, 125, 5, 0.05) !important;
    }

    .synced-line {
        font-family: monospace, sans-serif;
        background-color: #f8f9fa;
    }

    .synced-line.playing {
        color: #fd7d05 !important;
        font-weight: 600 !important;
        background-color: rgba(253, 125, 5, 0.05) !important;
    }

    .timestamp-container {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        gap: 8px;
    }

    .timestamp-value {
        flex: 1;
        text-align: center;
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

    .lyric-line:hover .timestamp-edit-btn {
        opacity: 1;
    }

    .timestamp-edit-btn:hover {
        color: #fd7d05;
        background-color: rgba(253, 125, 5, 0.1);
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
        background: rgba(253, 125, 5, 0.1);
        border-color: #fd7d05;
        color: #fd7d05;
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
        background-color: #fd7d05;
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
        background-color: #ff5e00;
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
        background-color: #fd7d05;
        color: white;
    }

    .btn-primary:hover {
        background-color: #e66c00;
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
        color: #ff9f4b;
        background-color: rgba(255, 159, 75, 0.1);
    }

    :global(body.dark) .space-parts {
        border-color: #444;
    }

    :global(body.dark) .left-part,
    :global(body.dark) .right-part {
        background-color: #2d2d2d;
    }

    :global(body.dark) .middle-part {
        background-color: #1e1e1e;
    }

    :global(body.dark) .left-part {
        border-right: 2px solid #ff9f4b !important;
    }

    :global(body.dark) .middle-part {
        border-right: 2px solid #ff9f4b !important;
    }

    :global(body.dark) .column-header {
        background-color: #3d3d3d;
        border-bottom-color: #444;
    }

    :global(body.dark) .column-header h3 {
        color: #e0e0e0;
    }

    :global(body.dark) .lyric-line {
        border-bottom-color: #444;
        color: #e0e0e0;
    }

    :global(body.dark) .lyric-line:hover {
        background-color: #3d3d3d;
    }

    :global(body.dark) .timestamp-line {
        background-color: #2d2d2d;
        color: #b0b0b0;
    }

    :global(body.dark) .synced-line {
        background-color: #2d2d2d;
    }

    :global(body.dark) .timestamp-edit-btn {
        color: #b0b0b0;
    }

    :global(body.dark) .timestamp-edit-btn:hover {
        color: #ff9f4b;
        background-color: rgba(255, 159, 75, 0.1);
    }

    :global(body.dark) .empty-state {
        color: #808080;
    }

    :global(body.dark) .insert-time-btn {
        background-color: #ff9f4b;
        color: #1e1e1e;
    }

    :global(body.dark) .insert-time-btn:hover:not(:disabled) {
        background-color: #ffb06f;
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
        background-color: #ff9f4b;
        color: #1e1e1e;
    }

    :global(body.dark) .btn-primary:hover {
        background-color: #ffb06f;
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
        background: rgba(255, 159, 75, 0.1);
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .header-btn.clear-timestamps {
        border-color: #ff6b6b;
        color: #ff6b6b;
    }

    :global(body.dark) .header-btn.clear-timestamps:hover {
        background: rgba(255, 107, 107, 0.2);
    }
</style>
