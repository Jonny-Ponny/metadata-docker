<!-- src/components/Player.svelte -->
<script>
    import { onMount } from "svelte";
    import { formatTimeDisplay } from "../utils/index.js";

    let { audioFile, ontimeupdate, ...rest } = $props();

    let audio = null;
    let playing = $state(false);
    let currentTime = $state(0);
    let duration = $state(0);
    let volume = $state(0.05);
    let waitingForMetadata = $state(false);
    let shouldAutoPlay = $state(false);

    // Helper to resolve a URL to an absolute string
    function resolveUrl(url) {
        try {
            return new URL(url, window.location.href).href;
        } catch {
            return url; // fallback
        }
    }

    // Helper to log with a consistent prefix
    function log(...args) {
        console.log("[Player]", ...args);
    }

    onMount(() => {
        log("Creating new Audio object");
        audio = new Audio();
        audio.volume = volume;

        audio.addEventListener("timeupdate", () => {
            currentTime = audio.currentTime;
            // log("timeupdate", currentTime);
            if (ontimeupdate) ontimeupdate(currentTime);
        });

        audio.addEventListener("loadedmetadata", () => {
            duration = audio.duration;
            log(
                "loadedmetadata, duration =",
                duration,
                "readyState =",
                audio.readyState,
            );
            waitingForMetadata = false;
            if (shouldAutoPlay) {
                log("Auto-playing after metadata loaded");
                audio
                    .play()
                    .then(() => {
                        playing = true;
                        log("Auto-play succeeded");
                    })
                    .catch((err) => {
                        console.error("[Player] Auto-play failed:", err);
                        playing = false;
                    });
                shouldAutoPlay = false;
            }
        });

        audio.addEventListener("ended", () => {
            log("ended event");
            playing = false;
        });

        audio.addEventListener("error", (e) => {
            console.error("[Player] Audio error:", audio.error);
        });

        audio.addEventListener("play", () => {
            log("play event (audio element)");
        });

        audio.addEventListener("pause", () => {
            log("pause event (audio element)");
        });

        audio.addEventListener("seeking", () => {
            log("seeking event, currentTime =", audio.currentTime);
        });

        audio.addEventListener("seeked", () => {
            log("seeked event, currentTime =", audio.currentTime);
        });

        audio.addEventListener("canplay", () => {
            log("canplay event, readyState =", audio.readyState);
        });

        audio.addEventListener("waiting", () => {
            log("waiting event");
        });

        return () => {
            log("Cleanup: pausing and clearing audio");
            if (audio) {
                audio.pause();
                audio.src = "";
            }
        };
    });

    async function togglePlay() {
        log("togglePlay called, playing =", playing, "audioFile =", audioFile);
        if (!audio || !audioFile) {
            log("togglePlay: no audio or audioFile, returning");
            return;
        }

        if (!audio.src) {
            log("Setting audio.src to", audioFile.url);
            audio.src = audioFile.url;
        }

        if (playing) {
            log("Pausing");
            audio.pause();
            playing = false;
            log("playing set to false");
        } else {
            try {
                log("Calling audio.play()");
                await audio.play();
                playing = true;
                log("Play succeeded, playing = true");
            } catch (err) {
                console.error("[Player] Playback failed:", err);
                playing = false;
            }
        }
    }

    function seek(e) {
        if (!audio || !duration) {
            log("seek: no audio or duration, returning");
            return;
        }
        const rect = e.currentTarget.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        const time = percent * duration;
        log("seek: setting currentTime to", time, "from click");
        audio.currentTime = time;
        if (ontimeupdate) ontimeupdate(time);
    }

    function setVolume(e) {
        volume = parseFloat(e.target.value);
        if (audio) audio.volume = volume;
        e.target.style.setProperty("--fill-percent", `${volume * 100}%`);
        log("setVolume:", volume);
    }

    function seekToTime(timeInSeconds) {
        log(
            "seekToTime called with",
            timeInSeconds,
            "audioFile =",
            audioFile,
            "audio =",
            audio,
        );
        if (!audio || !audioFile) {
            log("seekToTime: no audio or audioFile, returning false");
            return false;
        }
        if (!audio.src) {
            log("seekToTime: setting audio.src");
            audio.src = audioFile.url;
        }

        const doSeekAndPlay = () => {
            const targetTime = Math.max(
                0,
                Math.min(timeInSeconds, audio.duration || 0),
            );
            log("seekToTime: setting currentTime to", targetTime);
            audio.currentTime = targetTime;
            if (ontimeupdate) ontimeupdate(audio.currentTime);

            if (!playing) {
                log("seekToTime: starting playback (optimistic)");
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
            log(
                "seekToTime: waiting for metadata, readyState =",
                audio.readyState,
            );
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
        log("stop called");
        if (audio) {
            audio.pause();
            audio.src = "";
            audio.load();
            playing = false;
            currentTime = 0;
            duration = 0;
            log("stop completed");
        }
    }

    // Handle audio file changes – compare absolute URLs
    $effect(() => {
        log(
            "$effect: audioFile changed",
            audioFile,
            "audio?.src =",
            audio?.src,
        );
        if (audioFile && audioFile.url && audio) {
            const newUrl = resolveUrl(audioFile.url);
            const currentUrl = resolveUrl(audio.src || "");
            log(
                "$effect: resolved newUrl =",
                newUrl,
                "currentUrl =",
                currentUrl,
            );

            if (currentUrl !== newUrl) {
                const wasPlaying = playing;
                log(
                    "$effect: URL mismatch – setting new src. wasPlaying =",
                    wasPlaying,
                );
                audio.src = audioFile.url; // set with original string (browser will resolve)
                playing = false;
                currentTime = 0;
                duration = 0;
                waitingForMetadata = false;
                shouldAutoPlay = false;

                if (wasPlaying) {
                    log("$effect: was playing, will auto-play after metadata");
                    shouldAutoPlay = true;
                }
            } else {
                log("$effect: URLs match, no change");
            }
        } else {
            log("$effect: missing audioFile or audio");
        }
    });

    // Expose functions to parent
    export { seekToTime, stop };
</script>

<!-- Template – unchanged -->
<div class="player">
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div role="progressbar" class="progress-bar" onclick={seek}>
        <div
            class="progress"
            style={`width: ${duration ? (currentTime / duration) * 100 : 0}%`}
        ></div>
    </div>

    <div class="controls">
        <div class="filename" title={audioFile?.name || "No file loaded"}>
            {audioFile ? audioFile.name : "No file loaded"}
        </div>

        <button
            class="play-btn"
            onclick={togglePlay}
            disabled={!audioFile}
            title={playing ? "Pause" : "Play"}
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
                    oninput={setVolume}
                    class="volume-slider"
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
</style>
