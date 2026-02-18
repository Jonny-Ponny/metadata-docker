<!-- src/components/MetadataEditor.svelte -->
<script>
    import { toast } from "../utils/index.js";

    // Props
    let { filePath } = $props();

    // Reactive state for metadata (mock data for now)
    let metadata = $state({
        title: "",
        album: "",
        artist: "",
        track: "",
        disk: "",
        year: "",
        genre: "",
        comment: "",
        description: "",
        lyrics: "",
        unsyncedLyrics: "",
        otherFields: {
            composer: "",
            publisher: "",
        },
        picture: null,
    });

    // UI state
    let otherExpanded = $state(false);
    let customFields = $state([]); // { name: '', value: '' }

    // Track which field is being edited (by field name)
    let editingFields = $state(new Set());

    let customFieldEditing = $state([]);

    // Derived: filename from path
    let filename = $derived(filePath ? filePath.split(/[\\/]/).pop() : "");

    // Field definitions for main and always‑visible other fields
    const mainFields = [
        "title",
        "album",
        "artist",
        "albumArtist",
        "track",
        "disk",
        "year",
        "genre",
    ];

    const textareaFields = ["comment", "description"];

    function startEditing(fieldName) {
        editingFields.add(fieldName);
        editingFields = new Set(editingFields); // trigger reactivity
    }

    function stopEditing(fieldName) {
        // Small delay to allow clicking the icon before blur removes it
        setTimeout(() => {
            if (editingFields.has(fieldName)) {
                editingFields.delete(fieldName);
                editingFields = new Set(editingFields);
            }
        }, 150);
    }

    function addCustomField() {
        customFields = [...customFields, { name: "", value: "" }];
        customFieldEditing = [...customFieldEditing, false];
    }

    // Placeholder action handlers
    function applyToFile(field, value) {
        console.log(`Apply to file: ${field} = ${value}`);
        toast.success(`Updated ${field} for this file`);
    }

    function applyToFolder(field, value) {
        console.log(`Apply to folder: ${field} = ${value}`);
        toast.success(`Updated ${field} for all files in folder`);
    }

    async function fetchMetadata(path) {
        if (!path) return;

        try {
            const URL = `http://localhost:5000/api/metadata?path=${encodeURIComponent(path)}`; // development
            // const URL = `/api/metadata?path=${encodeURIComponent(path)}`; // build
            const response = await fetch(URL);

            if (!response.ok) {
                throw new Error(
                    `Failed to fetch metadata: ${response.statusText}`,
                );
            }

            const data = await response.json();

            // Fields that have dedicated top‑level properties in the component
            const mainFields = [
                "title",
                "album",
                "artist",
                "albumArtist",
                "track",
                "disk",
                "year",
                "genre",
            ];
            const specialFields = [
                "comment",
                "description",
                "lyrics",
                "unsyncedLyrics",
            ];
            const excludeFields = [
                ...mainFields,
                ...specialFields,
                "picture",
                "customFields",
                "otherFields",
            ];

            // Start with an empty otherFields object
            let other = {};

            // Add any top‑level fields that are not in excludeFields (e.g. composer, publisher)
            for (let key in data) {
                if (
                    !excludeFields.includes(key) &&
                    data[key] &&
                    typeof data[key] === "string"
                ) {
                    other[key] = data[key];
                }
            }

            // Add all entries from data.customFields (unknown tags)
            if (data.customFields && Array.isArray(data.customFields)) {
                for (let field of data.customFields) {
                    other[field.name] = field.value;
                }
            }

            // Merge any existing data.otherFields (for future compatibility)
            if (data.otherFields) {
                other = { ...other, ...data.otherFields };
            }

            // Update the main metadata object
            metadata = {
                title: data.title || "",
                album: data.album || "",
                artist: data.artist || "",
                albumArtist: data.albumArtist || "",
                track: data.track?.toString() || "",
                disk: data.disk?.toString() || "",
                year: data.year?.toString() || "",
                genre: data.genre || "",
                comment: data.comment || "",
                description: data.description || "",
                lyrics: data.lyrics || "",
                unsyncedLyrics: data.unsyncedLyrics || "",
                // @ts-ignore
                otherFields: other,
                picture: data.picture || null,
            };

            customFields = [];

            // toast.success("Metadata loaded successfully", 3000);
        } catch (error) {
            console.error("Error fetching metadata:", error);
            toast.error(`Failed to load metadata: ${error.message}`);
        }
    }

    $effect(() => {
        if (filePath) {
            fetchMetadata(filePath);
        }
    });
</script>

<div class="metadata-editor">
    <!-- Filename badge -->
    <div class="filename-badge">{filename}</div>

    <div class="cover-art">
        {#if metadata.picture}
            <img
                src={metadata.picture}
                alt="Cover Art"
                style="width:100%; height:100%; object-fit: cover;"
            />
        {:else}
            <!-- Cover art placeholder -->
            <svg
                width="100%"
                height="100%"
                viewBox="0 0 200 200"
                preserveAspectRatio="none"
            >
                <rect width="200" height="200" fill="#e0e0e0" />
                <text
                    x="50%"
                    y="50%"
                    dominant-baseline="middle"
                    text-anchor="middle"
                    fill="#999"
                    font-size="14"
                >
                    Album Art
                </text>
            </svg>
        {/if}
    </div>

    <!-- Main fields (all text inputs) -->
    <div class="fields-stack">
        {#each mainFields as field}
            {@const value = metadata[field]}
            <div class="field" class:editing={editingFields.has(field)}>
                <label for={field}
                    >{field.charAt(0).toUpperCase() + field.slice(1)}</label
                >
                <div class="input-wrapper">
                    <input
                        type="text"
                        id={field}
                        bind:value={metadata[field]}
                        onfocus={() => startEditing(field)}
                        onblur={() => stopEditing(field)}
                        placeholder={field}
                    />
                    {#if editingFields.has(field)}
                        <div class="field-actions">
                            <button
                                class="icon-btn"
                                title="Apply to this file only"
                                onclick={() => applyToFile(field, value)}
                            >
                                <!-- File icon -->
                                <svg
                                    width="14"
                                    height="16"
                                    viewBox="0 0 14 16"
                                    fill="none"
                                    xmlns="http://www.w3.org/2000/svg"
                                >
                                    <path
                                        d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                                        fill="currentColor"
                                        fill-opacity="0.7"
                                    />
                                    <path
                                        d="M10 1L12 3H10V1Z"
                                        fill="currentColor"
                                        fill-opacity="0.7"
                                    />
                                </svg>
                            </button>
                            <button
                                class="icon-btn"
                                title="Apply to all files in folder"
                                onclick={() => applyToFolder(field, value)}
                            >
                                <!-- Folder icon -->
                                <svg
                                    width="16"
                                    height="16"
                                    viewBox="0 0 16 16"
                                    fill="none"
                                    xmlns="http://www.w3.org/2000/svg"
                                >
                                    <path
                                        d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                                        fill="currentColor"
                                        fill-opacity="0.9"
                                    />
                                </svg>
                            </button>
                        </div>
                    {/if}
                </div>
            </div>
        {/each}
    </div>

    <!-- Other section (collapsible) -->
    <div class="other-section">
        <button
            class="collapse-toggle"
            onclick={() => (otherExpanded = !otherExpanded)}
        >
            {otherExpanded ? "X" : "▶"} Other
        </button>

        {#if otherExpanded}
            <div class="other-fields">
                <!-- Textarea fields (comment, description) -->
                {#each textareaFields as field}
                    {@const value = metadata[field]}
                    <div class="field" class:editing={editingFields.has(field)}>
                        <label for={field}
                            >{field.charAt(0).toUpperCase() +
                                field.slice(1)}</label
                        >
                        <div class="input-wrapper">
                            <textarea
                                id={field}
                                bind:value={metadata[field]}
                                onfocus={() => startEditing(field)}
                                onblur={() => stopEditing(field)}
                                placeholder={field}
                                rows="2"
                            ></textarea>
                            {#if editingFields.has(field)}
                                <div class="field-actions textarea-actions">
                                    <button
                                        aria-label="File"
                                        class="icon-btn"
                                        onclick={() =>
                                            applyToFile(field, value)}
                                    >
                                        <svg
                                            width="14"
                                            height="16"
                                            viewBox="0 0 14 16"
                                            fill="none"
                                            xmlns="http://www.w3.org/2000/svg"
                                        >
                                            <path
                                                d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                                                fill="currentColor"
                                                fill-opacity="0.7"
                                            />
                                            <path
                                                d="M10 1L12 3H10V1Z"
                                                fill="currentColor"
                                                fill-opacity="0.7"
                                            />
                                        </svg>
                                    </button>
                                    <button
                                        aria-label="Folder"
                                        class="icon-btn"
                                        onclick={() =>
                                            applyToFolder(field, value)}
                                    >
                                        <svg
                                            width="16"
                                            height="16"
                                            viewBox="0 0 16 16"
                                            fill="none"
                                            xmlns="http://www.w3.org/2000/svg"
                                        >
                                            <path
                                                d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                                                fill="currentColor"
                                                fill-opacity="0.9"
                                            />
                                        </svg>
                                    </button>
                                </div>
                            {/if}
                        </div>
                    </div>
                {/each}

                <!-- Other fields from metadata.otherFields -->
                {#each Object.entries(metadata.otherFields || {}) as [key, value]}
                    <div class="field">
                        <label for={key}>{key}</label>
                        <div class="input-wrapper">
                            <input
                                type="text"
                                id={key}
                                bind:value={metadata.otherFields[key]}
                                onfocus={() => startEditing(key)}
                                onblur={() => stopEditing(key)}
                            />
                            {#if editingFields.has(key)}
                                <div class="field-actions">
                                    <button
                                        aria-label="File"
                                        class="icon-btn"
                                        onclick={() => applyToFile(key, value)}
                                    >
                                        <svg
                                            width="14"
                                            height="16"
                                            viewBox="0 0 14 16"
                                            fill="none"
                                            xmlns="http://www.w3.org/2000/svg"
                                        >
                                            <path
                                                d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                                                fill="currentColor"
                                                fill-opacity="0.7"
                                            />
                                            <path
                                                d="M10 1L12 3H10V1Z"
                                                fill="currentColor"
                                                fill-opacity="0.7"
                                            />
                                        </svg>
                                    </button>
                                    <button
                                        aria-label="Folder"
                                        class="icon-btn"
                                        onclick={() =>
                                            applyToFolder(key, value)}
                                    >
                                        <svg
                                            width="16"
                                            height="16"
                                            viewBox="0 0 16 16"
                                            fill="none"
                                            xmlns="http://www.w3.org/2000/svg"
                                        >
                                            <path
                                                d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                                                fill="currentColor"
                                                fill-opacity="0.9"
                                            />
                                        </svg>
                                    </button>
                                </div>
                            {/if}
                        </div>
                    </div>
                {/each}

                <!-- Lyrics action buttons -->
                <div class="lyrics-actions">
                    <button
                        class="action-btn"
                        onclick={() => console.log("Edit lyrics")}
                    >
                        Edit lyrics
                    </button>
                    <button
                        class="action-btn"
                        onclick={() => console.log("Edit unsynced lyrics")}
                    >
                        Edit unsynced lyrics
                    </button>
                </div>
            </div>
        {/if}
    </div>

    <!-- Add new field button -->
    <button class="add-field-btn" onclick={addCustomField}>
        + Add new field
    </button>

    <!-- Custom fields added by user (now outside Other section) -->
    {#each customFields, index (index)}
        <div
            class="field custom"
            class:editing={customFieldEditing[index]}
            onfocusin={() => (customFieldEditing[index] = true)}
            onfocusout={(e) => {
                // If focus moves to an element outside this container, stop editing
                // @ts-ignore
                if (!e.currentTarget.contains(e.relatedTarget)) {
                    customFieldEditing[index] = false;
                }
            }}
        >
            <!-- Field name input -->
            <input
                type="text"
                placeholder="Field name"
                bind:value={customFields[index].name}
            />

            <!-- Value row: input and icons -->
            <div class="value-row">
                <input
                    type="text"
                    placeholder="Value"
                    bind:value={customFields[index].value}
                />
                {#if customFieldEditing[index]}
                    <div class="field-actions">
                        <button
                            aria-label="File"
                            class="icon-btn"
                            onclick={() =>
                                applyToFile(
                                    customFields[index].name,
                                    customFields[index].value,
                                )}
                        >
                            <!-- file icon svg -->
                            <svg
                                width="14"
                                height="16"
                                viewBox="0 0 14 16"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                            >
                                <path
                                    d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                                    fill="currentColor"
                                    fill-opacity="0.7"
                                />
                                <path
                                    d="M10 1L12 3H10V1Z"
                                    fill="currentColor"
                                    fill-opacity="0.7"
                                />
                            </svg>
                        </button>
                        <button
                            aria-label="Folder"
                            class="icon-btn"
                            onclick={() =>
                                applyToFolder(
                                    customFields[index].name,
                                    customFields[index].value,
                                )}
                        >
                            <!-- folder icon svg -->
                            <svg
                                width="16"
                                height="16"
                                viewBox="0 0 16 16"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                            >
                                <path
                                    d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                                    fill="currentColor"
                                    fill-opacity="0.9"
                                />
                            </svg>
                        </button>
                    </div>
                {/if}
            </div>
        </div>
    {/each}
</div>

<style>
    .metadata-editor {
        height: 100%;
        overflow-y: auto;
        padding: 16px;
        box-sizing: border-box;
    }

    input:focus,
    textarea:focus {
        outline: none;
        border-color: #fd7d05 !important; /* !important to override any existing border-color */
    }

    .filename-badge {
        font-size: 13px;
        color: #888;
        margin-bottom: 16px;
        text-align: center;
        max-width: 100%;
        word-break: break-all;
        white-space: normal; /* Allow wrapping */
        overflow: visible; /* Don't truncate */
        background: rgba(0, 0, 0, 0.03);
        padding: 4px 8px;
        border-radius: 4px;
    }

    .cover-art {
        width: 100%;
        aspect-ratio: 1 / 1;
        max-width: 200px;
        margin: 0 auto 20px;
        border-radius: 8px;
        overflow: hidden;
        background: #f0f0f0;
    }

    /* Stack fields vertically */
    .fields-stack {
        display: flex;
        flex-direction: column;
        gap: 16px;
        margin-bottom: 24px;
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 4px;
        width: 100%;
        position: relative;
    }

    .field label {
        font-size: 12px;
        font-weight: 500;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .input-wrapper {
        position: relative;
        display: flex;
        align-items: center;
        width: 100%;
    }

    /* Base input styles */
    .input-wrapper input,
    .input-wrapper textarea,
    .field.custom input {
        width: 100%;
        padding: 8px 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
        background: white;
        box-sizing: border-box;
    }

    /* Make space for icons when editing a standard field */
    .field.editing input,
    .field.editing textarea {
        padding-right: 70px;
    }

    .input-wrapper textarea {
        resize: vertical;
        min-height: 60px;
    }

    /* Icon container */
    .field-actions {
        display: flex;
        gap: 4px;
        flex-shrink: 0;
    }

    /* For textareas, align icons to the top */
    .textarea-actions {
        top: 12px;
        transform: none;
    }

    .icon-btn {
        background: none;
        border: none;
        cursor: pointer;
        padding: 4px;
        color: #666;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
    }

    .icon-btn:hover {
        background: rgba(0, 0, 0, 0.1);
        color: #fd7d05;
    }

    .other-section {
        margin-top: 20px;
        border-top: 1px solid #eee;
        padding-top: 16px;
    }

    .collapse-toggle {
        background: none;
        border: none;
        color: #fd7d05;
        font-weight: 600;
        font-size: 14px;
        cursor: pointer;
        padding: 4px 0;
        display: flex;
        align-items: center;
        gap: 4px;
    }

    .other-fields {
        margin-top: 16px;
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    /* Custom field container */
    .field.custom {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 16px;
        margin-bottom: 16px;
        width: 100%;
    }

    .add-field-btn {
        background: transparent;
        border: 1px dashed #fd7d05;
        color: #fd7d05;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 13px;
        cursor: pointer;
        margin-top: 20px;
        width: 100%;
    }

    .add-field-btn:hover {
        background: rgba(253, 125, 5, 0.1);
    }

    /* Value row: flex container for input + icons */
    .value-row {
        display: flex;
        align-items: center;
        gap: 4px;
        width: 100%;
    }

    /* Value input takes all available space */
    .value-row input {
        flex: 1;
        min-width: 0;
    }

    .lyrics-actions {
        display: flex;
        gap: 8px;
        margin-top: 16px;
    }

    .action-btn {
        background: transparent;
        border: 1px solid #fd7d05;
        color: #fd7d05;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 13px;
        cursor: pointer;
        flex: 1;
    }

    .action-btn:hover {
        background: rgba(253, 125, 5, 0.1);
    }

    /* Dark mode adjustments */
    :global(body.dark) .filename-badge {
        background: rgba(255, 255, 255, 0.1);
        color: #ccc;
    }

    :global(body.dark) .field label {
        color: #aaa;
    }

    :global(body.dark) .input-wrapper input,
    :global(body.dark) .input-wrapper textarea,
    :global(body.dark) .field.custom input {
        background: #3d3d3d;
        border-color: #555;
        color: #e0e0e0;
    }

    :global(body.dark) .field-actions {
        background: transparent;
    }

    :global(body.dark) .icon-btn {
        color: #aaa;
    }

    :global(body.dark) .icon-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: #ff9f4b;
    }

    :global(body.dark) .other-section {
        border-color: #444;
    }

    :global(body.dark) .action-btn {
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .action-btn:hover {
        background: rgba(255, 159, 75, 0.1);
    }
</style>
