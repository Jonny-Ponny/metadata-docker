<!-- src/components/Player.svelte -->
<script>
    import { onMount } from "svelte";
    import { formatTimeDisplay, settings } from "../utils/index.js";

    let { audioFile, ontimeupdate, ...rest } = $props();

    let audio = null;
    let playing = $state(false);
    let currentTime = $state(0);
    let duration = $state(0);
    let volume = $state(0.05);
    let waitingForMetadata = $state(false);
    let shouldAutoPlay = $state(false);

    const VOLUME_STORAGE_KEY = "player-volume";

    // Helper function to load saved volume
    function loadSavedVolume() {
        try {
            const saved = localStorage.getItem(VOLUME_STORAGE_KEY);
            if (saved !== null) {
                const parsed = parseFloat(saved);
                // Validate the value is between 0 and 1
                if (!isNaN(parsed) && parsed >= 0 && parsed <= 1) {
                    return parsed;
                }
            }
        } catch (err) {
            console.error(
                "[Player] Failed to load volume from localStorage:",
                err,
            );
        }
        return 0.05; // Default value
    }

    // Helper function to save volume
    function saveVolume(vol) {
        try {
            localStorage.setItem(VOLUME_STORAGE_KEY, vol.toString());
        } catch (err) {
            console.error(
                "[Player] Failed to save volume to localStorage:",
                err,
            );
        }
    }

    // Helper to resolve a URL to an absolute string
    function resolveUrl(url) {
        try {
            return new URL(url, window.location.href).href;
        } catch {
            return url; // fallback
        }
    }

    onMount(() => {
        volume = loadSavedVolume();
        audio = new Audio();
        audio.volume = volume;

        audio.addEventListener("timeupdate", () => {
            currentTime = audio.currentTime;
            if (ontimeupdate) ontimeupdate(currentTime);

            // Dispatch event for lyrics editor
            const event = new CustomEvent("player-time-update", {
                detail: { time: currentTime },
            });
            window.dispatchEvent(event);
        });

        audio.addEventListener("loadedmetadata", () => {
            duration = audio.duration;
            waitingForMetadata = false;
            if (shouldAutoPlay) {
                audio
                    .play()
                    .then(() => {
                        playing = true;
                    })
                    .catch((err) => {
                        console.error("[Player] Auto-play failed:", err);
                        playing = false;
                    });
                shouldAutoPlay = false;
            }
        });

        audio.addEventListener("ended", () => {
            playing = false;
        });

        audio.addEventListener("error", (e) => {
            console.error("[Player] Audio error:", audio.error);
        });

        audio.addEventListener("play", () => {});

        audio.addEventListener("pause", () => {});

        audio.addEventListener("seeking", () => {});

        audio.addEventListener("seeked", () => {});

        audio.addEventListener("canplay", () => {});

        audio.addEventListener("waiting", () => {});

        // Listen for lyrics-seek events (when user clicks on a timestamp/lyric line)
        const handleLyricsSeek = (e) => {
            const time = e.detail.time;
            seekToTime(time);
        };

        // Listen for get-current-time events (when sync button is pressed)
        const handleGetCurrentTime = (e) => {
            const callback = e.detail.callback;
            if (callback && typeof callback === "function") {
                callback(currentTime);
            }
        };

        window.addEventListener("lyrics-seek", handleLyricsSeek);
        window.addEventListener("get-current-time", handleGetCurrentTime);

        return () => {
            if (audio) {
                audio.pause();
                audio.src = "";
            }
            window.removeEventListener("lyrics-seek", handleLyricsSeek);
            window.removeEventListener(
                "get-current-time",
                handleGetCurrentTime,
            );
        };
    });

    async function togglePlay() {
        if (!audio || !audioFile) {
            return;
        }

        if (!audio.src) {
            audio.src = audioFile.url;
        }

        if (playing) {
            audio.pause();
            playing = false;
        } else {
            try {
                await audio.play();
                playing = true;
            } catch (err) {
                console.error("[Player] Playback failed:", err);
                playing = false;
            }
        }
    }

    function seek(e) {
        if (!audio || !duration) {
            return;
        }
        const rect = e.currentTarget.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        const time = percent * duration;
        audio.currentTime = time;
        if (ontimeupdate) ontimeupdate(time);
    }

    function setVolume(e) {
        volume = parseFloat(e.target.value);
        if (audio) audio.volume = volume;
        e.target.style.setProperty("--fill-percent", `${volume * 100}%`);

        // Save to localStorage
        saveVolume(volume);
    }

    function seekToTime(timeInSeconds) {
        if (!audio || !audioFile) {
            return false;
        }
        if (!audio.src) {
            audio.src = audioFile.url;
        }

        const doSeekAndPlay = () => {
            const targetTime = Math.max(
                0,
                Math.min(timeInSeconds, audio.duration || 0),
            );
            audio.currentTime = targetTime;
            if (ontimeupdate) ontimeupdate(audio.currentTime);

            if (!playing) {
                playing = true; // <-- optimistic update
                audio.play().catch((err) => {
                    console.error(
                        "[Player] Playback failed in seekToTime:",
                        err,
                    );
                    playing = false; // revert on failure
                });
            }
        };

        // If duration isn't known yet, wait for metadata
        if (!duration && audio.readyState < 1) {
            waitingForMetadata = true;
            const onLoaded = () => {
                audio.removeEventListener("loadedmetadata", onLoaded);
                if (waitingForMetadata) {
                    doSeekAndPlay();
                    waitingForMetadata = false;
                }
            };
            audio.addEventListener("loadedmetadata", onLoaded);
        } else {
            doSeekAndPlay();
        }
        return true;
    }

    function stop() {
        if (audio) {
            audio.pause();
            audio.src = "";
            audio.load();
            playing = false;
            currentTime = 0;
            duration = 0;
        }
    }

    // Handle audio file changes – compare absolute URLs
    $effect(() => {
        if (audioFile && audioFile.url && audio) {
            const newUrl = resolveUrl(audioFile.url);
            const currentUrl = resolveUrl(audio.src || "");

            if (currentUrl !== newUrl) {
                const wasPlaying = playing;
                audio.src = audioFile.url; // set with original string (browser will resolve)
                playing = false;
                currentTime = 0;
                duration = 0;
                waitingForMetadata = false;
                shouldAutoPlay = false;

                if (wasPlaying) {
                    shouldAutoPlay = true;
                }
            } else {
            }
        } else {
        }
    });

    function getCurrentTime() {
        return currentTime;
    }

    function handleVolumeScroll(e) {
        if (!$settings.enablePlayer) return;

        e.preventDefault(); // Prevent page scrolling

        // Adjust volume by 0.05 per scroll tick
        const delta = e.deltaY > 0 ? -0.05 : 0.05;
        let newVolume = volume + delta;

        // Clamp between 0 and 1
        newVolume = Math.max(0, Math.min(1, newVolume));

        if (newVolume !== volume) {
            volume = newVolume;
            if (audio) audio.volume = volume;

            // Update the input element's value and style
            const volumeInput = e.currentTarget;
            volumeInput.value = volume;
            volumeInput.style.setProperty(
                "--volume-percent",
                `${volume * 100}`,
            );

            // Save to localStorage
            saveVolume(volume);
        }
    }

    // Expose functions to parent
    export { seekToTime, stop, getCurrentTime };
</script>

<!-- Template – unchanged -->
<div class="player" class:player-disabled={!$settings.enablePlayer}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
        role="progressbar"
        class="progress-bar"
        onclick={$settings.enablePlayer ? seek : undefined}
    >
        <div
            class="progress"
            style={`width: ${duration ? (currentTime / duration) * 100 : 0}%`}
        ></div>
    </div>

    <div class="controls">
        <div class="filename" title={audioFile?.name || "No file loaded"}>
            {#if !$settings.enablePlayer}
                <span class="player-disabled-badge">Player Disabled</span>
            {/if}
            {audioFile ? audioFile.name : "No file loaded"}
        </div>

        <button
            class="play-btn"
            class:disabled={!$settings.enablePlayer || !audioFile}
            onclick={$settings.enablePlayer ? togglePlay : undefined}
            disabled={!$settings.enablePlayer || !audioFile}
            title={!$settings.enablePlayer
                ? "Player is disabled in settings"
                : playing
                  ? "Pause"
                  : "Play"}
        >
            {#if playing}
                <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                >
                    <rect x="6" y="4" width="4" height="16" />
                    <rect x="14" y="4" width="4" height="16" />
                </svg>
            {:else}
                <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                >
                    <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
            {/if}
        </button>

        <div class="time-volume">
            <div class="time">
                {formatTimeDisplay(currentTime)} / {formatTimeDisplay(duration)}
            </div>
            <div class="volume">
                <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                >
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                </svg>
                <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={volume}
                    oninput={$settings.enablePlayer ? setVolume : undefined}
                    onwheel={$settings.enablePlayer
                        ? handleVolumeScroll
                        : undefined}
                    disabled={!$settings.enablePlayer}
                    class="volume-slider"
                    class:disabled={!$settings.enablePlayer}
                    style={`--volume-percent: ${volume * 100}`}
                />
            </div>
        </div>
    </div>
</div>

<style>
    /* Player Styles */
    .player {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: white;
        border-top: 1px solid #ddd;
        padding: 0 20px;
        z-index: 1000;
    }

    .progress-bar {
        height: 3px;
        background: #e0e0e0;
        cursor: pointer;
    }

    .progress {
        height: 100%;
        background: #fd7d05;
        width: 0%;
        transition: width 0.1s;
    }

    .controls {
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 60px;
    }

    .filename {
        flex: 1;
        font-size: 14px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        padding-right: 10px;
    }

    .play-btn {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: #fd7d05;
        border: none;
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
    }

    .play-btn:hover {
        background: #ff5e00;
    }

    .play-btn:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

    .time-volume {
        flex: 1;
        text-align: right;
        font-size: 13px;
        color: #666;
        padding-left: 10px;
    }

    .time {
        margin-bottom: 4px;
    }

    .volume {
        display: flex;
        align-items: center;
        gap: 8px;
        justify-content: flex-end;
    }

    .volume-slider {
        width: 80px;
        height: 4px;
        background: #e0e0e0;
        border-radius: 2px;
        outline: none;
        appearance: none;
        position: relative;
    }

    /* Webkit browsers (Chrome, Safari, Edge) */
    .volume-slider::-webkit-slider-runnable-track {
        width: 100%;
        height: 4px;
        background: linear-gradient(
            to right,
            #fd7d05 calc(1% * var(--volume-percent, 30)),
            #e0e0e8 0
        );
        border-radius: 2px;
    }

    .volume-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 12px;
        height: 12px;
        border-radius: 2px;
        background: #fd7d05;
        cursor: pointer;
        margin-top: -4px;
        border: none;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    }

    /* Firefox */
    .volume-slider::-moz-range-track {
        width: 100%;
        height: 4px;
        background: #e0e0e0;
        border-radius: 2px;
    }

    .volume-slider::-moz-range-progress {
        background: #fd7d05;
        height: 4px;
        border-radius: 2px;
    }

    .volume-slider::-moz-range-thumb {
        width: 12px;
        height: 12px;
        border-radius: 2px;
        background: #fd7d05;
        cursor: pointer;
        border: none;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    }

    /* For Webkit browsers, set the CSS variable on the input element */
    input[type="range"].volume-slider {
        --volume-percent: 30;
        /* Default - will be overridden by inline style */
    }

    .player-disabled-badge {
        background: #888;
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        margin-right: 8px;
        text-transform: uppercase;
    }

    .player-disabled .progress-bar {
        cursor: not-allowed;
        opacity: 0.5;
    }

    .player-disabled .progress {
        background: #888;
    }

    .play-btn.disabled {
        background: #ccc;
        cursor: not-allowed;
    }

    .volume-slider.disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    /* Dark mode player styles */
    :global(body.dark) .player {
        background: #2d2d2d;
        border-top-color: #444;
    }

    :global(body.dark) .progress-bar {
        background: #444;
    }

    :global(body.dark) .progress {
        background: #ff9f4b; /* Slightly lighter orange for dark mode */
    }

    :global(body.dark) .filename {
        color: #e0e0e0;
    }

    :global(body.dark) .play-btn {
        background: #fd7d05;
        color: #1e1e1e; /* Dark text on orange button for contrast */
    }

    :global(body.dark) .play-btn:hover:not(:disabled) {
        background: #ff9f4b;
    }

    :global(body.dark) .play-btn:disabled {
        background: #444;
        color: #666;
        opacity: 0.5;
    }

    :global(body.dark) .time-volume {
        color: #b0b0b0;
    }

    :global(body.dark) .time {
        color: #b0b0b0;
    }

    :global(body.dark) .volume-slider {
        background: #444;
    }

    /* Webkit browsers (Chrome, Safari, Edge) dark mode */
    :global(body.dark) .volume-slider::-webkit-slider-runnable-track {
        background: linear-gradient(
            to right,
            #ff9f4b calc(1% * var(--volume-percent, 30)),
            #444 0
        );
    }

    :global(body.dark) .volume-slider::-webkit-slider-thumb {
        background: #ff9f4b;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
    }

    /* Firefox dark mode */
    :global(body.dark) .volume-slider::-moz-range-track {
        background: #444;
    }

    :global(body.dark) .volume-slider::-moz-range-progress {
        background: #ff9f4b;
    }

    :global(body.dark) .volume-slider::-moz-range-thumb {
        background: #ff9f4b;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
    }

    :global(body.dark) .player-disabled-badge {
        background: #666;
        color: #ccc;
    }

    :global(body.dark) .player-disabled .progress {
        background: #666;
    }
</style>
