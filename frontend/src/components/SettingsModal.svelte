<script>
    import { onMount } from "svelte";
    import {
        settings,
        saveSettings,
        ALLOWED_VARIABLES,
    } from "../utils/index.js";

    let { isOpen, onClose } = $props();

    // Local state for form
    let localSettings = $state({ ...$settings });

    // Mock data for preview
    const mockMetadata = {
        title: "THE DYING MESSAGE",
        album: "悪巫山戯",
        artist: "鬱P",
        albumArtist: "鬱P",
        year: "2013",
        track: "12",
    };

    // Generate preview from scheme
    function getPreview(scheme, isFile = false) {
        if (!scheme) return isFile ? "filename.flac" : "Folder Name";

        let preview = scheme;

        // Replace variables with mock data
        preview = preview.replace(/\[TITLE\]/g, mockMetadata.title);
        preview = preview.replace(/\[ALBUM\]/g, mockMetadata.album);
        preview = preview.replace(/\[ARTIST\]/g, mockMetadata.artist);
        preview = preview.replace(/\[ALBUMARTIST\]/g, mockMetadata.albumArtist);
        preview = preview.replace(/\[YYYY\]/g, mockMetadata.year);
        preview = preview.replace(/\[TRACK\]/g, mockMetadata.track);

        // Clean up
        preview = preview.replace(/\s+/g, " ").trim();

        // Add extension for file preview
        if (isFile) {
            return preview + ".flac";
        }

        return preview || "Folder Name";
    }

    // Handle escape key to close
    function handleKeyDown(e) {
        if (e.key === "Escape" && isOpen) {
            onClose();
        }
    }

    onMount(() => {
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    });

    function handleModalClick(e) {
        e.stopPropagation();
    }

    function handleSave() {
        saveSettings(localSettings);
        onClose();
    }

    function handleCancel() {
        localSettings = { ...$settings };
        onClose();
    }

    function insertVariable(type, variable) {
        if (type === "folder") {
            localSettings.folderScheme += variable;
        } else {
            localSettings.fileScheme += variable;
        }
        // Trigger reactivity
        localSettings = { ...localSettings };
    }

    // Variable descriptions
    const variableDescriptions = {
        TITLE: "Song title. Fundamental field that identifies the specific name of an individual piece of music",
        ALBUM: "Album name. Field used to store the name of the collection a song belongs to",
        ARTIST: "Artist name. Identifies the specific performer(s) for a single song",
        ALBUMARTIST:
            "Album artist. Specific field used to identify the primary artist or group responsible for an entire album. It is separate from the standard Artist (or Track Artist) tag, which identifies the performer(s) on an individual song",
        YYYY: "Year (from date field)",
        TRACK: "Track number (padded: 01, 02, etc.)",
    };
</script>

{#if isOpen}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="settings-modal-overlay" onclick={onClose}>
        <div class="settings-modal" onclick={handleModalClick}>
            <!-- Header -->
            <div class="settings-modal-header">
                <h2>Settings</h2>
                <button class="close-btn" onclick={onClose} title="Close (Esc)">
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

            <!-- Content -->
            <div class="settings-content">
                <!-- General Settings -->
                <div class="settings-section">
                    <h3>General</h3>
                    <div class="setting-item">
                        <label class="checkbox-label">
                            <input
                                type="checkbox"
                                bind:checked={localSettings.allowDeleteKey}
                            />
                            <span>Allow Delete key to delete files/folders</span
                            >
                        </label>
                        <p class="setting-description">
                            When enabled, pressing Delete while a file/folder is
                            selected will delete it immediately.
                        </p>
                    </div>
                </div>

                <!-- Folder Renaming Scheme -->
                <div class="settings-section">
                    <h3>Folder Renaming Scheme</h3>
                    <p class="section-description">
                        This scheme will be used when renaming folders.
                        Variables in [BRACKETS] will be replaced with actual
                        values.
                    </p>

                    <div class="scheme-input-group">
                        <input
                            type="text"
                            class="scheme-input"
                            bind:value={localSettings.folderScheme}
                            placeholder="e.g., [[YYYY]]_[ARTIST]_[ALBUM]"
                        />
                    </div>

                    <div class="variable-buttons">
                        <strong>Click to insert variables:</strong>
                        <div class="variable-tags">
                            {#each Object.keys(ALLOWED_VARIABLES) as variable}
                                <button
                                    class="variable-tag"
                                    onclick={() =>
                                        insertVariable(
                                            "folder",
                                            `[${variable}]`,
                                        )}
                                    title={variableDescriptions[variable]}
                                >
                                    [{variable}]
                                </button>
                            {/each}
                        </div>
                    </div>

                    <div class="example-preview">
                        <strong>Preview:</strong>
                        <code class="preview-scheme"
                            >{localSettings.folderScheme ||
                                "[[YYYY]]_[ARTIST]_[ALBUM]"}</code
                        >
                        <span class="example-arrow">→</span>
                        <code class="preview-result"
                            >{getPreview(localSettings.folderScheme)}</code
                        >
                    </div>
                </div>

                <!-- File Renaming Scheme -->
                <div class="settings-section">
                    <h3>File Renaming Scheme</h3>
                    <p class="section-description">
                        This scheme will be used when renaming files. The file
                        extension will be automatically preserved.
                    </p>

                    <div class="scheme-input-group">
                        <input
                            type="text"
                            class="scheme-input"
                            bind:value={localSettings.fileScheme}
                            placeholder="e.g., [TRACK]_[TITLE]"
                        />
                    </div>

                    <div class="variable-buttons">
                        <strong>Click to insert variables:</strong>
                        <div class="variable-tags">
                            {#each Object.keys(ALLOWED_VARIABLES) as variable}
                                <button
                                    class="variable-tag"
                                    onclick={() =>
                                        insertVariable("file", `[${variable}]`)}
                                    title={variableDescriptions[variable]}
                                >
                                    [{variable}]
                                </button>
                            {/each}
                        </div>
                    </div>

                    <div class="example-preview">
                        <strong>Preview:</strong>
                        <code class="preview-scheme"
                            >{localSettings.fileScheme ||
                                "[TRACK]_[TITLE]"}</code
                        >
                        <span class="example-arrow">→</span>
                        <code class="preview-result"
                            >{getPreview(localSettings.fileScheme, true)}</code
                        >
                    </div>

                    <p class="note">
                        <strong>Note:</strong> Only the variables shown above will
                        be replaced. Any other text, brackets, or symbols will stay
                        exactly as written.
                    </p>
                </div>
            </div>

            <!-- Footer -->
            <div class="settings-modal-footer">
                <button class="cancel-btn" onclick={handleCancel}>Cancel</button
                >
                <button class="save-btn" onclick={handleSave}
                    >Save Settings</button
                >
            </div>
        </div>
    </div>
{/if}

<style>
    .settings-modal-overlay {
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
        overflow: hidden; /* Prevent overlay scroll */
    }

    .settings-modal {
        background: white;
        border-radius: 12px;
        width: 90%;
        max-width: 700px;
        max-height: 85vh;
        display: flex;
        flex-direction: column;
        animation: scaleIn 0.2s ease;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        overflow: hidden; /* Prevent modal scroll */
    }

    .settings-modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 24px;
        border-bottom: 1px solid #eee;
        background: #fafafa;
        flex-shrink: 0; /* Prevent header from shrinking */
    }

    .settings-modal-header h2 {
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
        flex-shrink: 0; /* Prevent button from shrinking */
    }

    .close-btn:hover {
        background: rgba(0, 0, 0, 0.1);
        color: #fd7d05;
    }

    .settings-content {
        flex: 1;
        overflow-y: auto;
        padding: 24px;
        padding-right: 20px;
    }

    /* Custom scrollbar for webkit browsers */
    .settings-content::-webkit-scrollbar {
        width: 8px;
    }

    .settings-content::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
    }

    .settings-content::-webkit-scrollbar-thumb {
        background: #ccc;
        border-radius: 4px;
    }

    .settings-content::-webkit-scrollbar-thumb:hover {
        background: #999;
    }

    .settings-section {
        margin-bottom: 32px;
        width: 100%;
        box-sizing: border-box;
    }

    .settings-section h3 {
        margin: 0 0 16px 0;
        font-size: 16px;
        font-weight: 600;
        color: #fd7d05;
        border-bottom: 1px solid #eee;
        padding-bottom: 8px;
    }

    .section-description {
        margin: 0 0 16px 0;
        font-size: 13px;
        color: #666;
        line-height: 1.5;
    }

    .setting-item {
        margin-bottom: 16px;
    }

    .checkbox-label {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        font-weight: 500;
        color: #333;
    }

    .checkbox-label input[type="checkbox"] {
        width: 16px;
        height: 16px;
        cursor: pointer;
        accent-color: #fd7d05;
        flex-shrink: 0;
    }

    .setting-description {
        margin: 4px 0 0 24px;
        font-size: 12px;
        color: #888;
    }

    .scheme-input-group {
        margin-bottom: 16px;
        width: 100%;
        box-sizing: border-box;
    }

    .scheme-input {
        width: 100%;
        padding: 10px 12px;
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 14px;
        font-family: monospace;
        box-sizing: border-box; /* Critical for preventing overflow */
        max-width: 100%; /* Ensure it doesn't exceed container */
    }

    .scheme-input:focus {
        outline: none;
        border-color: #fd7d05;
    }

    .variable-buttons {
        margin-bottom: 16px;
        width: 100%;
        box-sizing: border-box;
    }

    .variable-buttons strong {
        display: block;
        font-size: 12px;
        color: #666;
        margin-bottom: 8px;
    }

    .variable-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        width: 100%;
    }

    .variable-tag {
        background: transparent;
        border: 1px solid #fd7d05;
        color: #fd7d05;
        padding: 6px 12px;
        border-radius: 4px;
        font-size: 12px;
        font-family: monospace;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
    }

    .variable-tag:hover {
        background: rgba(253, 125, 5, 0.1);
    }

    .example-preview {
        background: #f5f5f5;
        padding: 12px;
        border-radius: 6px;
        font-size: 13px;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        width: 100%;
        box-sizing: border-box;
    }

    .example-preview strong {
        color: #666;
        flex-shrink: 0;
    }

    .example-preview code {
        background: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-family: monospace;
        word-break: break-all; /* Allow long text to wrap */
        max-width: 100%;
    }

    .preview-scheme {
        color: #fd7d05;
        flex: 1;
        min-width: 0; /* Allow flex item to shrink */
    }

    .preview-result {
        color: #fd7d05;
        flex: 1;
        min-width: 0;
    }

    .example-arrow {
        color: #fd7d05;
        font-weight: bold;
        flex-shrink: 0;
    }

    .note {
        margin-top: 12px;
        padding: 8px 12px;
        background: #fff3e0;
        border-left: 3px solid #fd7d05;
        font-size: 12px;
        color: #555;
        width: 100%;
        box-sizing: border-box;
    }

    .settings-modal-footer {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 12px;
        padding: 16px 24px;
        border-top: 1px solid #eee;
        background: #fafafa;
        flex-shrink: 0; /* Prevent footer from shrinking */
    }

    .cancel-btn {
        background: transparent;
        border: 1px solid #ddd;
        padding: 8px 24px;
        border-radius: 6px;
        font-size: 14px;
        color: #666;
        cursor: pointer;
        transition: all 0.2s;
    }

    .cancel-btn:hover {
        background: #f0f0f0;
        border-color: #fd7d05;
        color: #fd7d05;
    }

    .save-btn {
        background: #fd7d05;
        border: none;
        padding: 8px 24px;
        border-radius: 6px;
        font-size: 14px;
        color: white;
        cursor: pointer;
        transition: all 0.2s;
    }

    .save-btn:hover {
        background: #e66d00;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(253, 125, 5, 0.3);
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

    /* Dark mode */
    :global(body.dark) .settings-modal {
        background: #2d2d2d;
    }

    :global(body.dark) .settings-modal-header {
        background: #383838;
        border-color: #444;
    }

    :global(body.dark) .settings-modal-header h2 {
        color: #e0e0e0;
    }

    :global(body.dark) .close-btn {
        color: #aaa;
    }

    :global(body.dark) .close-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: #ff9f4b;
    }

    :global(body.dark) .settings-section h3 {
        color: #ff9f4b;
        border-color: #444;
    }

    :global(body.dark) .section-description,
    :global(body.dark) .setting-description,
    :global(body.dark) .variable-buttons strong {
        color: #aaa;
    }

    :global(body.dark) .checkbox-label {
        color: #e0e0e0;
    }

    :global(body.dark) .scheme-input {
        background: #3d3d3d;
        border-color: #555;
        color: #e0e0e0;
    }

    :global(body.dark) .example-preview {
        background: #383838;
        color: #e0e0e0;
    }

    :global(body.dark) .example-preview code {
        background: #2d2d2d;
        color: #ff9f4b;
    }

    :global(body.dark) .example-preview strong {
        color: #aaa;
    }

    :global(body.dark) .preview-result {
        color: #6fcf97;
    }

    :global(body.dark) .note {
        background: #3d3d3d;
        color: #b0b0b0;
    }

    :global(body.dark) .settings-modal-footer {
        background: #383838;
        border-color: #444;
    }

    :global(body.dark) .cancel-btn {
        border-color: #555;
        color: #aaa;
    }

    :global(body.dark) .cancel-btn:hover {
        background: #444;
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .settings-content::-webkit-scrollbar-track {
        background: #383838;
    }

    :global(body.dark) .settings-content::-webkit-scrollbar-thumb {
        background: #555;
    }

    :global(body.dark) .settings-content::-webkit-scrollbar-thumb:hover {
        background: #666;
    }
</style>
