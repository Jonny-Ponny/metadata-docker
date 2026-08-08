<script>
    import { toast } from "../utils/index.js";

    let { filePath } = $props();

    let content = $state("");
    let isLoading = $state(true);
    let isSaving = $state(false);
    let error = $state("");

    async function loadText() {
        isLoading = true;
        error = "";
        try {
            const res = await fetch(`/api/text?path=${encodeURIComponent(filePath)}`);
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || "Failed to load text");
            }
            const data = await res.json();
            content = data.content || "";
        } catch (e) {
            error = e.message;
            toast.error(error);
        } finally {
            isLoading = false;
        }
    }

    async function saveText() {
        isSaving = true;
        try {
            const res = await fetch("/api/text/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: filePath, content }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || "Save failed");
            }
            toast.success("Text saved");
        } catch (e) {
            toast.error(`Save error: ${e.message}`);
        } finally {
            isSaving = false;
        }
    }

    async function copyToClipboard() {
        try {
            await navigator.clipboard.writeText(content);
            toast.success("Copied to clipboard");
        } catch {
            // fallback
            const textarea = document.querySelector("textarea");
            if (textarea) {
                textarea.select();
                document.execCommand("copy");
                toast.success("Copied to clipboard");
            }
        }
    }

    // Reload when filePath changes
    $effect(() => {
        if (filePath) {
            loadText();
        }
    });
</script>

<div class="text-editor">
    {#if isLoading}
        <div class="loading">Loading…</div>
    {:else if error}
        <div class="error">{error}</div>
    {:else}
        <div class="toolbar">
            <button class="btn save-btn" onclick={saveText} disabled={isSaving}>
                {#if isSaving}Saving…{:else}Save{/if}
            </button>
            <button class="btn copy-btn" onclick={copyToClipboard}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <span>Copy to clipboard</span>
            </button>
        </div>
        <textarea bind:value={content} spellcheck="false"></textarea>
    {/if}
</div>

<style>
    .text-editor {
        height: 100%;
        display: flex;
        flex-direction: column;
        padding: 16px;
        box-sizing: border-box;
    }

    .toolbar {
        display: flex;
        gap: 8px;
        margin-bottom: 12px;
        flex-shrink: 0;
    }

    .btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        height: 34px;
        border: 1px solid #ddd;
        border-radius: 4px;
        background: transparent;
        font-size: 13px;
        color: #666;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
    }

    .btn svg {
        width: 16px;
        height: 16px;
        flex-shrink: 0;
    }

    .btn:hover:not(:disabled) {
        background: rgba(253, 125, 5, 0.1);
        border-color: #fd7d05;
        color: #fd7d05;
    }

    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .save-btn,
    .copy-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        height: 34px;
        border: 1px solid #ddd;
        border-radius: 4px;
        background: transparent;
        font-size: 13px;
        color: #666;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
    }

    textarea {
        flex: 1;
        width: 100%;
        padding: 10px;
        font-family: monospace;
        font-size: 14px;
        line-height: 1.5;
        border: 1px solid #ddd;
        border-radius: 4px;
        resize: none;
        box-sizing: border-box;
        background: white;
        color: #333;
    }

    textarea:focus {
        outline: none;
        border-color: #fd7d05;
    }

    .loading,
    .error {
        text-align: center;
        padding: 20px;
        color: #888;
    }

    .error {
        color: #d32f2f;
    }

    :global(body.dark) .btn {
        border-color: #555;
        color: #aaa;
    }

    :global(body.dark) .btn:hover:not(:disabled) {
        background: rgba(255, 159, 75, 0.15);
        border-color: #ff9f4b;
        color: #ff9f4b;
    }

    :global(body.dark) .btn:disabled {
        opacity: 0.4;
    }

    :global(body.dark) textarea {
        background: #3d3d3d;
        border-color: #555;
        color: #e0e0e0;
    }
</style>