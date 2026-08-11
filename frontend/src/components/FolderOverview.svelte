<!-- src/components/FolderOverview.svelte -->
<script>
    let { folderPath, audioFiles } = $props();

    let files = $derived(Array.isArray(audioFiles) ? audioFiles : []);

    let loading = $state(true);
    let error = $state(null);
    let fileResults = $state({});

    const MAIN_FIELDS = [
        "title",
        "album",
        "artist",
        "albumArtist",
        "track",
        "disk",
        "year",
        "genre",
        "unsyncedLyrics",
        "lyrics",
    ];

    $effect(() => {
        if (folderPath && files.length > 0) {
            fetchAllMetadata();
        } else {
            loading = false;
            fileResults = {};
        }
    });

    async function fetchAllMetadata() {
        loading = true;
        error = null;
        fileResults = {};

        const concurrency = 5;
        const filesCopy = [...files];
        let index = 0;

        async function fetchNext() {
            if (index >= filesCopy.length) return;
            const file = filesCopy[index++];
            try {
                const meta = await fetchMetadata(file.path);
                const missing = MAIN_FIELDS.filter((f) => {
                    const val = meta[f];
                    return (
                        val === undefined ||
                        val === null ||
                        (typeof val === "string" && val.trim() === "")
                    );
                });
                fileResults[file.path] = { missingFields: missing };
            } catch (err) {
                console.error("Failed to fetch metadata for", file.path, err);
                fileResults[file.path] = { error: err.message };
            }
            await fetchNext();
        }

        const workers = [];
        for (let i = 0; i < Math.min(concurrency, filesCopy.length); i++) {
            workers.push(fetchNext());
        }
        await Promise.all(workers);

        loading = false;
    }

    async function fetchMetadata(path) {
        const res = await fetch(
            `/api/metadata?path=${encodeURIComponent(path)}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    }

    function getFilesWithMissing() {
        const result = [];
        for (const file of files) {
            const info = fileResults[file.path];
            if (info && info.missingFields && info.missingFields.length > 0) {
                result.push({ ...file, missingFields: info.missingFields });
            }
        }
        return result;
    }

    function getErrorCount() {
        let count = 0;
        for (const file of files) {
            if (fileResults[file.path] && fileResults[file.path].error) count++;
        }
        return count;
    }

    const missingFiles = $derived(getFilesWithMissing());
    const errorCount = $derived(getErrorCount());
    const totalFiles = $derived(files.length);
</script>

<div class="folder-overview">
    {#if loading}
        <div class="loading-state">Loading folder overview…</div>
    {:else if error}
        <div class="error-state">
            <p>Error: {error}</p>
            <button onclick={fetchAllMetadata}>Retry</button>
        </div>
    {:else}
        <div class="summary">
            {#if missingFiles.length === 0 && errorCount === 0}
                <p class="all-complete">
                    All files have all main metadata fields
                </p>
            {:else}
                <p class="missing-count">
                    {missingFiles.length} of {totalFiles} files have missing fields
                    {#if errorCount > 0}
                        <span class="error-note"
                            >(and {errorCount} failed to load)</span
                        >
                    {/if}
                </p>
            {/if}
        </div>

        {#if missingFiles.length > 0}
            <div class="file-list">
                <h5>Files with missing fields</h5>
                <ul>
                    {#each missingFiles as file}
                        <li>
                            <div class="file-entry">
                                <span class="file-name">{file.name}</span>
                                <ul class="missing-list">
                                    {#each file.missingFields as field}
                                        <li>{field}</li>
                                    {/each}
                                </ul>
                            </div>
                        </li>
                    {/each}
                </ul>
            </div>
        {/if}

        <button class="refresh-btn" onclick={fetchAllMetadata}>Refresh</button>
    {/if}
</div>

<style>
    .folder-overview {
        height: 100%;
        overflow-y: auto;
        padding: 16px;
        box-sizing: border-box;
        font-size: 14px;
    }
    .loading-state {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100%;
        color: #888;
    }
    .error-state {
        text-align: center;
        color: #d32f2f;
    }
    .error-state button {
        margin-top: 8px;
    }
    .summary {
        margin-bottom: 20px;
    }
    .missing-count {
        font-weight: 500;
        color: #d84315;
        font-size: 15px;
    }
    .all-complete {
        color: #2e7d32;
        font-weight: 500;
        font-size: 15px;
    }
    .error-note {
        color: #888;
        font-weight: normal;
        font-size: 0.9em;
    }
    .file-list h5 {
        margin: 16px 0 12px;
        font-weight: 600;
        font-size: 15px;
    }
    .file-list ul {
        list-style: none;
        padding: 0;
        margin: 0;
    }
    .file-list li {
        padding: 8px 0;
    }
    .file-entry {
        display: block;
    }
    .file-name {
        font-weight: 600;
        color: #333;
        font-size: 15px;
        display: block;
        margin-bottom: 4px;
    }
    .missing-list {
        list-style: disc;
        margin: 2px 0 2px 24px;
        padding: 0;
    }
    .missing-list li {
        border: none;
        padding: 0;
        margin: 2px 0;
        font-size: 14px;
        color: #d84315;
    }
    .refresh-btn {
        margin-top: 20px;
        background: transparent;
        border: 1px solid #fd7d05;
        color: #fd7d05;
        padding: 6px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
    }
    .refresh-btn:hover {
        background: rgba(253, 125, 5, 0.1);
    }

    /* Dark mode */
    :global(body.dark) .file-list li {
        border-color: #444;
    }
    :global(body.dark) .file-name {
        color: #e0e0e0;
    }
    :global(body.dark) .missing-count {
        color: #ff8a65;
    }
    :global(body.dark) .missing-list li {
        color: #ff8a65;
    }
    :global(body.dark) .all-complete {
        color: #66bb6a;
    }
    :global(body.dark) .error-note {
        color: #aaa;
    }
</style>
