<!-- src/components/LogViewer.svelte -->
<script>
    import { toast, getAuthHeaders } from "../utils/index.js";

    let { isOpen, onClose } = $props();

    // State using $state rune
    let logs = $state([]);
    let loading = $state(false);
    let error = $state(null);
    let linesToShow = $state(100);
    let levelFilter = $state("");
    let searchFilter = $state("");
    let autoRefresh = $state(false);
    let refreshInterval = $state(null);
    let hasMounted = $state(false);

    // Derived values using $derived
    let hasFilters = $derived(levelFilter || searchFilter);
    let filteredCount = $derived(logs.length);

    // Available log levels
    const logLevels = ["INFO", "WARNING", "ERROR", "DEBUG"];

    // Methods (not using runes)
    async function fetchLogs() {
        loading = true;
        error = null;

        try {
            const params = new URLSearchParams();
            params.append("lines", String(linesToShow));
            if (levelFilter) params.append("level", levelFilter);
            if (searchFilter) params.append("search", searchFilter);

            const headers = getAuthHeaders();

            const response = await fetch(`/api/logs?${params}`, {
                headers,
            });

            const data = await response.json();

            if (response.ok) {
                logs = data.logs || [];
            } else {
                error = data.error || "Failed to fetch logs";
                console.error("Log fetch error:", data);
            }
        } catch (err) {
            error = "Network error: " + err.message;
            console.error("Log fetch exception:", err);
        } finally {
            loading = false;
        }
    }

    async function clearLogs() {
        try {
            const headers = getAuthHeaders();
            headers["Content-Type"] = "application/json";

            const response = await fetch("/api/logs/clear", {
                method: "POST",
                headers,
            });

            const data = await response.json();

            if (response.ok) {
                logs = [];
                toast.success("Logs cleared successfully");
            } else {
                toast.error(data.error || "Failed to clear logs");
            }
        } catch (err) {
            toast.error("Network error: " + err.message);
        }
    }

    function downloadLogs() {
        const logText = logs
            .map((log) => {
                if (log.timestamp) {
                    return `[${log.timestamp}] [${log.level}] ${log.message}`;
                }
                return log.raw;
            })
            .join("\n");

        const blob = new Blob([logText], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `logs_${new Date().toISOString().slice(0, 10)}.log`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function getLevelClass(level) {
        if (!level) return "";

        const levelLower = level.toLowerCase();
        switch (levelLower) {
            case "error":
                return "log-level-error";
            case "warning":
            case "warn":
                return "log-level-warning";
            case "info":
                return "log-level-info";
            case "debug":
                return "log-level-debug";
            default:
                return "";
        }
    }

    function handleKeyDown(e) {
        if (e.key === "Escape" && isOpen) {
            e.preventDefault();
            e.stopPropagation();
            onClose();
        }
    }

    function stopPropagation(e) {
        e.stopPropagation();
    }

    function handleOverlayClick(e) {
        // Only close if clicking directly on the overlay, not its children
        if (e.target === e.currentTarget) {
            e.preventDefault();
            e.stopPropagation();
            onClose();
        }
    }

    function handleCloseClick(e) {
        e.preventDefault();
        e.stopPropagation();
        onClose();
    }

    // Effects using $effect
    $effect(() => {
        // Handle auto-refresh
        if (autoRefresh && isOpen) {
            if (refreshInterval) clearInterval(refreshInterval);
            refreshInterval = setInterval(() => {
                fetchLogs();
            }, 5000);

            return () => {
                clearInterval(refreshInterval);
                refreshInterval = null;
            };
        } else if (refreshInterval) {
            clearInterval(refreshInterval);
            refreshInterval = null;
        }
    });

    $effect(() => {
        // Initial fetch when modal opens
        if (isOpen && !hasMounted) {
            hasMounted = true;
            fetchLogs();
        }
    });

    $effect(() => {
        // Setup keyboard listener
        if (isOpen) {
            window.addEventListener("keydown", handleKeyDown);
            return () => {
                window.removeEventListener("keydown", handleKeyDown);
            };
        }
    });
</script>

{#if isOpen}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="log-modal-overlay" onclick={handleOverlayClick}>
        <div class="log-modal" onclick={stopPropagation}>
            <!-- Header -->
            <div class="log-modal-header">
                <h2>Application Logs</h2>
                <button
                    class="close-btn"
                    onclick={handleCloseClick}
                    title="Close (Esc)"
                >
                    <svg width="20" height="20" viewBox="0 0 20 20">
                        <path
                            d="M15 5L5 15M5 5L15 15"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                        />
                    </svg>
                </button>
            </div>

            <!-- Controls -->
            <div class="log-controls">
                <div class="control-group">
                    <select
                        bind:value={linesToShow}
                        onchange={fetchLogs}
                        class="log-select"
                    >
                        <option value={50}>50 lines</option>
                        <option value={100}>100 lines</option>
                        <option value={500}>500 lines</option>
                        <option value={1000}>1000 lines</option>
                    </select>

                    <select
                        bind:value={levelFilter}
                        onchange={fetchLogs}
                        class="log-select"
                    >
                        <option value="">All Levels</option>
                        {#each logLevels as level}
                            <option value={level}>{level}</option>
                        {/each}
                    </select>

                    <div class="search-container">
                        <input
                            type="text"
                            bind:value={searchFilter}
                            placeholder="Search logs..."
                            oninput={fetchLogs}
                            class="log-search"
                        />
                        {#if searchFilter}
                            <button
                                class="search-clear"
                                onclick={() => {
                                    searchFilter = "";
                                    fetchLogs();
                                }}
                                title="Clear search"
                            >
                                <svg width="14" height="14" viewBox="0 0 24 24">
                                    <line x1="18" y1="6" x2="6" y2="18" />
                                    <line x1="6" y1="6" x2="18" y2="18" />
                                </svg>
                            </button>
                        {/if}
                    </div>
                </div>

                <div class="action-group">
                    <label class="auto-refresh">
                        <input type="checkbox" bind:checked={autoRefresh} />
                        <span>Auto-refresh (5s)</span>
                    </label>

                    <button
                        class="log-btn refresh-btn"
                        onclick={fetchLogs}
                        disabled={loading}
                    >
                        {#if loading}
                            <svg
                                class="spinner"
                                width="16"
                                height="16"
                                viewBox="0 0 24 24"
                            >
                                <circle
                                    cx="12"
                                    cy="12"
                                    r="10"
                                    stroke="currentColor"
                                    stroke-width="2"
                                    fill="none"
                                    stroke-dasharray="32"
                                >
                                    <animateTransform
                                        attributeName="transform"
                                        type="rotate"
                                        from="0 12 12"
                                        to="360 12 12"
                                        dur="1s"
                                        repeatCount="indefinite"
                                    />
                                </circle>
                            </svg>
                            Loading...
                        {:else}
                            <svg
                                width="16"
                                height="16"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                            >
                                <path d="M23 4v6h-6M1 20v-6h6" />
                                <path
                                    d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"
                                />
                            </svg>
                            Refresh
                        {/if}
                    </button>

                    <button class="log-btn download-btn" onclick={downloadLogs}>
                        <svg
                            width="16"
                            height="16"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                        >
                            <path
                                d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
                            />
                            <polyline points="7 10 12 15 17 10" />
                            <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        Download
                    </button>

                    <button class="log-btn clear-btn" onclick={clearLogs}>
                        <svg
                            width="16"
                            height="16"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                        >
                            <polyline points="3 6 5 6 21 6" />
                            <path
                                d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0h4M10 11v5M14 11v5"
                            />
                        </svg>
                        Clear
                    </button>
                </div>
            </div>

            <!-- Log display -->
            <div class="log-display">
                {#if loading && logs.length === 0}
                    <div class="log-empty">
                        <svg
                            class="spinner"
                            width="48"
                            height="48"
                            viewBox="0 0 24 24"
                        >
                            <circle
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                stroke-width="2"
                                fill="none"
                                stroke-dasharray="32"
                            >
                                <animateTransform
                                    attributeName="transform"
                                    type="rotate"
                                    from="0 12 12"
                                    to="360 12 12"
                                    dur="1s"
                                    repeatCount="indefinite"
                                />
                            </circle>
                        </svg>
                        <p>Loading logs...</p>
                    </div>
                {:else if error}
                    <div class="log-error">
                        <svg
                            width="48"
                            height="48"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="8" x2="12" y2="12" />
                            <circle
                                cx="12"
                                cy="16"
                                r="0.5"
                                fill="currentColor"
                            />
                        </svg>
                        <p>{error}</p>
                        <button class="retry-btn" onclick={fetchLogs}
                            >Retry</button
                        >
                    </div>
                {:else if logs.length === 0}
                    <div class="log-empty">
                        <svg
                            width="48"
                            height="48"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.5"
                        >
                            <path
                                d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
                            />
                            <polyline points="14 2 14 8 20 8" />
                            <line x1="16" y1="13" x2="8" y2="13" />
                            <line x1="16" y1="17" x2="8" y2="17" />
                        </svg>
                        <p>No logs to display</p>
                    </div>
                {:else}
                    <div class="log-entries">
                        {#each logs as log, index (index)}
                            <div class="log-entry {getLevelClass(log.level)}">
                                {#if log.timestamp}
                                    <span class="log-timestamp"
                                        >[{log.timestamp}]</span
                                    >
                                    <span
                                        class="log-level {getLevelClass(
                                            log.level,
                                        )}">[{log.level}]</span
                                    >
                                    <span class="log-message"
                                        >{log.message}</span
                                    >
                                {:else}
                                    <span class="log-raw">{log.raw}</span>
                                {/if}
                            </div>
                        {/each}
                    </div>
                {/if}
            </div>

            <!-- Footer with stats -->
            <div class="log-footer">
                <div class="log-stats">
                    <span>Showing {filteredCount} entries</span>
                    {#if hasFilters}
                        <span class="filter-badge">
                            {#if levelFilter}Level: {levelFilter}{/if}
                            {#if levelFilter && searchFilter}
                                •
                            {/if}
                            {#if searchFilter}Search: "{searchFilter}"{/if}
                        </span>
                    {/if}
                </div>
                <button class="close-footer-btn" onclick={handleCloseClick}
                    >Close</button
                >
            </div>
        </div>
    </div>
{/if}

<!-- Keep all the CSS from the previous version - it's the same -->
<style>
    .log-modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        animation: fadeIn 0.2s ease;
        backdrop-filter: blur(3px);
    }

    .log-modal {
        background: white;
        border-radius: 12px;
        width: 90%;
        max-width: 1000px;
        height: 80vh;
        display: flex;
        flex-direction: column;
        animation: scaleIn 0.2s ease;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        overflow: hidden;
    }

    .log-modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 24px;
        border-bottom: 1px solid #eee;
        background: #fafafa;
    }

    .log-modal-header h2 {
        margin: 0;
        font-size: 20px;
        font-weight: 600;
        color: #333;
    }

    .close-btn {
        background: none;
        border: none;
        cursor: pointer;
        padding: 8px;
        color: #666;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
        transition: all 0.2s;
    }

    .close-btn:hover {
        background: rgba(0, 0, 0, 0.1);
        color: #fd7d05;
    }

    .log-controls {
        padding: 16px 24px;
        background: #f5f5f5;
        border-bottom: 1px solid #e0e0e0;
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        align-items: center;
        justify-content: space-between;
    }

    .control-group {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }

    .action-group {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }

    .log-select {
        padding: 8px 12px;
        border: 1px solid #ddd;
        border-radius: 6px;
        background: white;
        color: #333;
        font-size: 13px;
        min-width: 120px;
    }

    .log-select:focus {
        outline: none;
        border-color: #fd7d05;
    }

    .search-container {
        position: relative;
        display: flex;
        align-items: center;
    }

    .log-search {
        padding: 8px 12px;
        padding-right: 30px;
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 13px;
        width: 200px;
        background: white;
        color: #333;
    }

    .log-search:focus {
        outline: none;
        border-color: #fd7d05;
    }

    .search-clear {
        position: absolute;
        right: 4px;
        background: none;
        border: none;
        padding: 4px;
        cursor: pointer;
        color: #999;
        display: flex;
        align-items: center;
        border-radius: 50%;
        transition: all 0.2s;
    }

    .search-clear:hover {
        color: #fd7d05;
        background: rgba(253, 125, 5, 0.1);
    }

    .auto-refresh {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        color: #666;
        cursor: pointer;
        padding: 0 8px;
    }

    .auto-refresh input[type="checkbox"] {
        cursor: pointer;
        accent-color: #fd7d05;
    }

    .log-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        border: 1px solid #ddd;
        border-radius: 6px;
        background: white;
        color: #666;
        font-size: 13px;
        cursor: pointer;
        transition: all 0.2s;
    }

    .log-btn:hover:not(:disabled) {
        background: #f0f0f0;
        border-color: #fd7d05;
        color: #fd7d05;
    }

    .log-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .refresh-btn {
        min-width: 90px;
    }

    .download-btn {
        color: #4a5568;
        border-color: #4a5568;
    }

    .download-btn:hover:not(:disabled) {
        background: #4a5568;
        color: white;
        border-color: #4a5568;
    }

    .clear-btn {
        color: #dc3545;
        border-color: #dc3545;
    }

    .clear-btn:hover:not(:disabled) {
        background: #dc3545;
        color: white;
        border-color: #dc3545;
    }

    .spinner {
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        from {
            transform: rotate(0deg);
        }
        to {
            transform: rotate(360deg);
        }
    }

    .log-display {
        flex: 1;
        overflow-y: auto;
        padding: 16px 24px;
        background: #fafafa;
    }

    .log-entries {
        font-family: "Monaco", "Menlo", "Courier New", monospace;
        font-size: 12px;
        line-height: 1.5;
    }

    .log-entry {
        padding: 4px 8px;
        border-bottom: 1px solid #eee;
        white-space: pre-wrap;
        word-break: break-word;
    }

    .log-entry:hover {
        background: #f0f0f0;
    }

    .log-timestamp {
        color: #888;
        margin-right: 8px;
    }

    .log-level {
        font-weight: 600;
        margin-right: 8px;
    }

    .log-message {
        color: #333;
    }

    .log-raw {
        color: #666;
    }

    .log-error {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 200px;
        gap: 12px;
        color: #dc3545;
        text-align: center;
    }

    .log-empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 200px;
        gap: 16px;
        color: #999;
    }

    .retry-btn {
        background: #fd7d05;
        color: white;
        border: none;
        padding: 8px 24px;
        border-radius: 6px;
        font-size: 14px;
        cursor: pointer;
        transition: all 0.2s;
    }

    .retry-btn:hover {
        background: #ff5e00;
    }

    .log-footer {
        padding: 12px 24px;
        border-top: 1px solid #eee;
        background: #fafafa;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .log-stats {
        font-size: 13px;
        color: #666;
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .filter-badge {
        background: #fd7d05;
        color: white;
        padding: 2px 8px;
        border-radius: 2px;
        font-size: 11px;
    }

    .close-footer-btn {
        background: transparent;
        border: 1px solid #ddd;
        padding: 6px 24px;
        border-radius: 6px;
        font-size: 13px;
        color: #666;
        cursor: pointer;
        transition: all 0.2s;
    }

    .close-footer-btn:hover {
        background: #f0f0f0;
        border-color: #fd7d05;
        color: #fd7d05;
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
            opacity: 0;
        }
        to {
            transform: scale(1);
            opacity: 1;
        }
    }

    .log-level.log-level-error {
        color: #dc3545;
    }
    .log-level.log-level-warning {
        color: #fd7d05;
    }
    .log-level.log-level-info {
        color: #0d6efd;
    }
    .log-level.log-level-debug {
        color: #6c757d;
    }

    /* Dark mode */
    :global(body.dark) .log-modal {
        background: #2d2d2d;
    }

    :global(body.dark) .log-modal-header {
        background: #383838;
        border-color: #444;
    }

    :global(body.dark) .log-modal-header h2 {
        color: #e0e0e0;
    }

    :global(body.dark) .close-btn {
        color: #aaa;
    }

    :global(body.dark) .close-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: #ff9f4b;
    }

    :global(body.dark) .log-controls {
        background: #333;
        border-color: #444;
    }

    :global(body.dark) .log-select {
        background: #3d3d3d;
        border-color: #555;
        color: #e0e0e0;
    }

    :global(body.dark) .log-search {
        background: #3d3d3d;
        border-color: #555;
        color: #e0e0e0;
    }

    :global(body.dark) .search-clear {
        color: #aaa;
    }

    :global(body.dark) .auto-refresh {
        color: #b0b0b0;
    }

    :global(body.dark) .log-btn {
        background: #3d3d3d;
        border-color: #555;
        color: #b0b0b0;
    }

    :global(body.dark) .log-btn:hover:not(:disabled) {
        background: #4a4a4a;
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .download-btn {
        color: #8b9dc3;
        border-color: #8b9dc3;
    }

    :global(body.dark) .download-btn:hover:not(:disabled) {
        background: #8b9dc3;
        border-color: #8b9dc3;
        color: #1e1e1e;
    }

    :global(body.dark) .clear-btn {
        color: #f28b82;
        border-color: #f28b82;
    }

    :global(body.dark) .clear-btn:hover:not(:disabled) {
        background: #f28b82;
        border-color: #f28b82;
        color: #1e1e1e;
    }

    :global(body.dark) .refresh-btn:hover:not(:disabled) {
        background: #4a4a4a;
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .log-display {
        background: #262626;
    }

    :global(body.dark) .log-entry {
        border-color: #3d3d3d;
    }

    :global(body.dark) .log-entry:hover {
        background: #333;
    }

    :global(body.dark) .log-timestamp {
        color: #aaa;
    }

    :global(body.dark) .log-message {
        color: #e0e0e0;
    }

    :global(body.dark) .log-raw {
        color: #b0b0b0;
    }

    :global(body.dark) .log-footer {
        background: #383838;
        border-color: #444;
    }

    :global(body.dark) .log-stats {
        color: #b0b0b0;
    }

    :global(body.dark) .filter-badge {
        background: #ff9f4b;
        color: #1e1e1e;
    }

    :global(body.dark) .close-footer-btn {
        border-color: #555;
        color: #b0b0b0;
    }

    :global(body.dark) .close-footer-btn:hover {
        background: #444;
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .log-level.log-level-error {
        color: #f28b82;
    }
    :global(body.dark) .log-level.log-level-warning {
        color: #ff9f4b;
    }
    :global(body.dark) .log-level.log-level-info {
        color: #8ab4f8;
    }
    :global(body.dark) .log-level.log-level-debug {
        color: #9aa0a6;
    }
</style>
