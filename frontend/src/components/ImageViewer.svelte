<!-- src/components/ImageViewer.svelte -->
<script>
    import { toast } from "../utils/index.js";

    let { filePath } = $props();

    let imageUrl = $state(null);
    let isLoading = $state(true);
    let error = $state(null);
    let showFullImage = $state(false);

    let filename = $derived(filePath ? filePath.split(/[\\/]/).pop() : "");

    $effect(() => {
        if (filePath) {
            loadImage();
        }

        return () => {
            if (imageUrl?.startsWith("blob:")) {
                URL.revokeObjectURL(imageUrl);
            }
        };
    });

    async function loadImage() {
        if (!filePath) return;

        isLoading = true;
        error = null;

        try {
            const url = `/api/image?path=${encodeURIComponent(filePath)}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Failed to load image: ${response.statusText}`);
            }

            const blob = await response.blob();
            if (imageUrl?.startsWith("blob:")) {
                URL.revokeObjectURL(imageUrl);
            }
            imageUrl = URL.createObjectURL(blob);
        } catch (err) {
            error = err.message;
            toast.error(`Failed to load image: ${err.message}`);
        } finally {
            isLoading = false;
        }
    }

    function openFullImage() {
        showFullImage = true;
    }

    function closeFullImage() {
        showFullImage = false;
    }
</script>

<div class="image-viewer">
    <div class="viewer-header">
        <div class="filename-badge">{filename}</div>
    </div>

    <div class="image-container">
        {#if isLoading}
            <div class="loading-state">
                <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                >
                    <circle
                        cx="12"
                        cy="12"
                        r="10"
                        stroke-dasharray="32"
                        stroke-dashoffset="32"
                    >
                        <animate
                            attributeName="stroke-dashoffset"
                            values="32;0"
                            dur="1s"
                            repeatCount="indefinite"
                        />
                    </circle>
                </svg>
                <p>Loading image...</p>
            </div>
        {:else if error}
            <div class="error-state">
                <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                >
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <circle cx="12" cy="16" r="0.5" fill="currentColor" />
                </svg>
                <p>Failed to load image</p>
                <p class="error-details">{error}</p>
                <button class="retry-btn" onclick={loadImage}>Retry</button>
            </div>
        {:else if imageUrl}
            <div class="image-wrapper">
                <img src={imageUrl} alt={filename} />
                <div class="image-overlay">
                    <div class="expand-corner">
                        <button
                            class="icon-btn expand-btn"
                            title="View full size"
                            onclick={openFullImage}
                        >
                            <svg
                                viewBox="0 0 20 20"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                                width="20"
                                height="20"
                            >
                                <path
                                    d="M7 3H4.5C4 3 4 3 4 3.5V6M17 6V4C17 3 17 3 16 3H14M14 16H16C17 16 17 16 17 15V13M4 13V15C4 16 4 16 5 16H7"
                                    stroke="currentColor"
                                    stroke-width="1.8"
                                    stroke-linecap="round"
                                />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>

<!-- Full-size image modal -->
{#if showFullImage && imageUrl}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div role="img" class="full-image-modal" onclick={closeFullImage}>
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="modal-content" onclick={(e) => e.stopPropagation()}>
            <button
                class="modal-close-btn"
                title="Close"
                onclick={closeFullImage}
            >
                <svg
                    width="20"
                    height="20"
                    viewBox="0 0 20 20"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                >
                    <path
                        d="M15 5L5 15M5 5L15 15"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                    />
                </svg>
            </button>
            <img src={imageUrl} alt="Full size cover art" />
        </div>
    </div>
{/if}

<style>
    .image-viewer {
        height: 100%;
        overflow-y: auto;
        padding: 16px;
        box-sizing: border-box;
    }

    .viewer-header {
        margin-bottom: 16px;
    }

    .filename-badge {
        font-size: 13px;
        color: #888;
        text-align: center;
        word-break: break-all;
        white-space: normal;
        background: rgba(0, 0, 0, 0.03);
        padding: 4px 8px;
        border-radius: 4px;
    }

    .image-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 300px;
    }

    .image-wrapper {
        position: relative;
        max-width: 100%;
        max-height: 500px;
        border-radius: 8px;
        overflow: hidden;
    }

    .image-wrapper img {
        max-width: 100%;
        max-height: 500px;
        object-fit: contain;
        display: block;
    }

    .image-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.3);
        opacity: 0;
        transition: opacity 0.2s;
        border-radius: 8px;
    }

    .image-wrapper:hover .image-overlay {
        opacity: 1;
    }

    .expand-corner {
        position: absolute;
        top: 8px;
        left: 8px;
        z-index: 15;
    }

    .expand-corner .icon-btn {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(4px);
        border-radius: 4px;
        padding: 8px;
        color: #333;
        border: none;
        cursor: pointer;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        transition: all 0.2s;
    }

    .expand-corner .icon-btn:hover {
        background: #fd7d05;
        color: white;
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(253, 125, 5, 0.3);
    }

    .expand-corner .icon-btn svg {
        width: 14px;
        height: 16px;
        display: block;
    }

    .loading-state,
    .error-state {
        text-align: center;
        color: #666;
        padding: 32px;
    }

    .error-details {
        font-size: 12px;
        color: #ff4444;
        margin-top: 8px;
    }

    .retry-btn {
        background: #fd7d05;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        margin-top: 12px;
        cursor: pointer;
    }

    .full-image-modal {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.95);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        cursor: pointer;
        animation: fadeIn 0.2s ease;
        padding-bottom: 60px; /* Move image up to avoid player */
    }

    .modal-content {
        position: relative;
        max-width: 90vw;
        max-height: 85vh;
        animation: scaleIn 0.2s ease;
        margin-top: -20px; /* Fine-tune vertical position */
    }

    .modal-content img {
        max-width: 100%;
        max-height: 85vh;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    }

    .modal-close-btn {
        position: absolute;
        top: 12px;
        right: 12px;
        width: 36px;
        height: 36px;
        transition: all 0.2s;
        backdrop-filter: blur(4px);
        z-index: 10001;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
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

    .modal-close-btn:hover {
        background: #fd7d05;
        border-color: rgba(255, 255, 255, 0.4);
        transform: scale(1.05);
        color: white;
    }

    .modal-close-btn svg {
        width: 18px;
        height: 18px;
        stroke: currentColor;
        stroke-width: 2.2;
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

    .icon-btn {
        background: none;
        border: none;
        cursor: pointer;
        padding: 0;
        color: #666;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        width: 32px;
        height: 32px;
    }

    .icon-btn:hover {
        background: rgba(0, 0, 0, 0.1);
        color: #fd7d05;
    }

    /* Dark mode */
    :global(body.dark) .filename-badge {
        background: rgba(255, 255, 255, 0.1);
        color: #ccc;
    }

    :global(body.dark) .expand-corner .icon-btn {
        /* background: rgba(61, 61, 61, 0.9); */
        backdrop-filter: blur(4px);
        color: #e0e0e0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }

    :global(body.dark) .expand-corner .icon-btn:hover {
        background: #ff9f4b;
        color: #1e1e1e;
        box-shadow: 0 4px 12px rgba(255, 159, 75, 0.3);
    }

    /* Dark mode adjustments */
    :global(body.dark) .expand-btn {
        background: rgba(61, 61, 61, 0.9);
        color: #e0e0e0;
    }

    :global(body.dark) .expand-btn:hover {
        background: #3d3d3d;
        color: #ff9f4b;
    }

    :global(body.dark) .modal-close-btn {
        border-color: rgba(255, 255, 255, 0.15);
    }

    :global(body.dark) .modal-close-btn:hover {
        background: #ff9f4b;
        border-color: rgba(255, 255, 255, 0.3);
        color: #1e1e1e;
    }
</style>
