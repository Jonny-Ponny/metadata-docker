<!-- src/components/BulkEditor.svelte -->
<script>
  import { untrack } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import { toast } from "../stores/toast.store.js";
  import { getAuthHeaders } from "../stores/auth.store.js";
  import { readApiError } from "../utils/api.utils.js";
  import {
    BULK_EDITABLE_FIELDS,
    getFieldLabel,
    getFieldDescription,
  } from "../utils/fieldMetadata.utils.js";
  import {
    BULK_FILE_LIMIT,
    buildBatchBody,
    collectAudioFiles,
    computeCommonValues,
    isValidDiskNumber,
  } from "../utils/bulkEdit.utils.js";

  /**
   * @typedef {import("../utils/bulkEdit.utils.js").BulkTreeNode} BulkTreeNode
   * @typedef {import("../utils/bulkEdit.utils.js").FieldEdit} FieldEdit
   */

  /**
   * @typedef {Object} Props
   * @property {BulkTreeNode | null} [folderNode]
   */

  /** @type {Props} */
  let { folderNode = null } = $props();

  let includeSubfolders = $state(false);
  let files = $derived(collectAudioFiles(folderNode, includeSubfolders));
  let limitReached = $derived(files.length >= BULK_FILE_LIMIT);

  const selected = new SvelteSet(/** @type {string[]} */ ([]));
  let lastClickedIndex = $state(/** @type {number | null} */ (null));

  let metadataByPath = $state(
    /** @type {Record<string, Record<string, unknown>>} */ ({}),
  );
  let loadFailures = $state(0);
  let loading = $state(false);

  let edits = $state(/** @type {Record<string, FieldEdit>} */ ({}));
  let confirming = $state(false);
  let saving = $state(false);

  let selectedPaths = $derived(
    files.map((file) => file.path).filter((path) => selected.has(path)),
  );
  let common = $derived(
    computeCommonValues(
      selectedPaths
        .map((path) => metadataByPath[path])
        .filter((meta) => meta !== undefined),
      BULK_EDITABLE_FIELDS,
    ),
  );
  let editEntries = $derived(Object.entries(edits));
  let diskNumberError = $derived.by(() => {
    const edit = edits.diskNumber;
    return edit?.action === "set" && !isValidDiskNumber(edit.value)
      ? 'Use a number like "1" or "1/2"'
      : "";
  });
  let canApply = $derived(
    selectedPaths.length > 0 &&
      editEntries.length > 0 &&
      !diskNumberError &&
      !loading &&
      !saving,
  );

  // Compared as a string so a tree reload with the same files keeps the
  // current selection and edits.
  let fileKey = $derived(files.map((file) => file.path).join("\n"));

  // A new folder or subfolder toggle starts a fresh session: every file is
  // selected and nothing is edited.
  $effect(() => {
    const paths = fileKey ? fileKey.split("\n") : [];
    untrack(() => {
      selected.clear();
      for (const path of paths) selected.add(path);
      lastClickedIndex = null;
      edits = {};
      confirming = false;
      loadMetadata(paths, true);
    });
  });

  /**
   * @param {string[]} paths
   * @param {boolean} [replace]
   */
  async function loadMetadata(paths, replace = false) {
    if (replace) {
      metadataByPath = {};
      loadFailures = 0;
    }
    if (paths.length === 0) return;
    loading = true;

    const queue = [...paths];
    let failures = 0;

    async function worker() {
      while (queue.length > 0) {
        const path = /** @type {string} */ (queue.shift());
        try {
          const response = await fetch(
            `/api/metadata?path=${encodeURIComponent(path)}&includePicture=false`,
            { headers: getAuthHeaders() },
          );
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          metadataByPath[path] = await response.json();
        } catch (err) {
          console.error("Failed to fetch metadata for", path, err);
          failures++;
        }
      }
    }

    await Promise.all(
      Array.from({ length: Math.min(5, paths.length) }, () => worker()),
    );
    loadFailures = replace ? failures : loadFailures + failures;
    loading = false;
  }

  /**
   * @param {number} index
   * @param {MouseEvent} event
   */
  function toggleFile(index, event) {
    const path = files[index].path;
    const shouldSelect = !selected.has(path);

    if (event.shiftKey && lastClickedIndex !== null) {
      const start = Math.min(lastClickedIndex, index);
      const end = Math.max(lastClickedIndex, index);
      for (let i = start; i <= end; i++) {
        if (shouldSelect) selected.add(files[i].path);
        else selected.delete(files[i].path);
      }
    } else if (shouldSelect) {
      selected.add(path);
    } else {
      selected.delete(path);
    }
    lastClickedIndex = index;
  }

  function toggleAll() {
    if (selectedPaths.length === files.length) {
      selected.clear();
    } else {
      for (const file of files) selected.add(file.path);
    }
  }

  /**
   * @param {string} field
   * @param {string} value
   */
  function setField(field, value) {
    const shared = common[field];
    if (shared && !shared.mixed && value === shared.value) {
      resetField(field);
      return;
    }
    edits[field] = { action: "set", value };
  }

  /**
   * @param {string} field
   */
  function deleteField(field) {
    edits[field] = { action: "delete" };
  }

  /**
   * @param {string} field
   */
  function resetField(field) {
    const { [field]: _removed, ...rest } = edits;
    edits = rest;
  }

  /**
   * @param {string} field
   * @returns {string}
   */
  function inputValue(field) {
    const edit = edits[field];
    if (edit?.action === "set") return edit.value;
    if (edit?.action === "delete") return "";
    return common[field]?.value ?? "";
  }

  async function applyChanges() {
    if (!canApply) return;
    saving = true;
    const paths = [...selectedPaths];

    try {
      const response = await fetch("/api/metadata/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify(buildBatchBody(paths, edits)),
      });
      if (!response.ok) {
        toast.error(await readApiError(response, "Bulk update failed"));
        return;
      }

      const result = await response.json();
      /** @type {string[]} */
      const failedFiles = result.failed_files ?? [];
      if (failedFiles.length > 0) {
        toast.warning(
          `${result.message}. Failed: ${failedFiles.join(", ")}`,
          8000,
        );
      } else {
        toast.success(result.message || "Bulk update complete");
      }

      edits = {};
      confirming = false;
      const failed = new Set(failedFiles);
      await loadMetadata(paths.filter((path) => !failed.has(path)));
    } catch (err) {
      toast.error(
        `Bulk update failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      saving = false;
    }
  }
</script>

<div class="bulk-editor">
  <div class="toolbar">
    <label class="subfolder-toggle">
      <input type="checkbox" bind:checked={includeSubfolders} />
      Include subfolders
    </label>
    <span class="selection-count">
      {selectedPaths.length} of {files.length} files selected
    </span>
  </div>

  {#if limitReached}
    <p class="note">
      Limited to the first {BULK_FILE_LIMIT} audio files.
    </p>
  {/if}

  {#if files.length === 0}
    <p class="empty">No audio files in this folder.</p>
  {:else}
    <div class="file-list">
      <label class="file-row select-all">
        <input
          type="checkbox"
          checked={selectedPaths.length === files.length}
          indeterminate={selectedPaths.length > 0 &&
            selectedPaths.length < files.length}
          onchange={toggleAll}
        />
        Select all
      </label>
      {#each files as file, index (file.path)}
        <label class="file-row">
          <input
            type="checkbox"
            checked={selected.has(file.path)}
            onclick={(event) => {
              event.preventDefault();
              toggleFile(index, event);
            }}
          />
          <span class="file-name">{file.relativePath}</span>
        </label>
      {/each}
    </div>

    {#if loading}
      <p class="note">Loading tags…</p>
    {:else if loadFailures > 0}
      <p class="note warning">
        Could not read tags for {loadFailures} file(s); shared values may be incomplete.
      </p>
    {/if}

    <form
      class="fields"
      onsubmit={(event) => {
        event.preventDefault();
        if (canApply) confirming = true;
      }}
    >
      {#each BULK_EDITABLE_FIELDS as field (field)}
        {@const edit = edits[field]}
        <div
          class="field-row"
          class:changed={edit?.action === "set"}
          class:deleted={edit?.action === "delete"}
        >
          <label for={`bulk-${field}`} title={getFieldDescription(field)}>
            {getFieldLabel(field)}
          </label>
          <input
            id={`bulk-${field}`}
            type="text"
            value={inputValue(field)}
            placeholder={edit?.action === "delete"
              ? "(will be removed)"
              : common[field]?.mixed
                ? "(multiple values)"
                : ""}
            disabled={edit?.action === "delete" || saving}
            oninput={(event) => setField(field, event.currentTarget.value)}
          />
          {#if edit}
            <button
              type="button"
              class="field-action"
              onclick={() => resetField(field)}
              aria-label={`Undo ${getFieldLabel(field)} change`}
            >
              Undo
            </button>
          {:else}
            <button
              type="button"
              class="field-action"
              onclick={() => deleteField(field)}
              aria-label={`Remove ${getFieldLabel(field)} from all`}
              title="Remove this tag from every selected file"
            >
              Remove
            </button>
          {/if}
        </div>
        {#if field === "diskNumber" && diskNumberError}
          <p class="field-error" role="alert">{diskNumberError}</p>
        {/if}
      {/each}

      {#if confirming}
        <div class="confirm" role="region" aria-label="Confirm bulk changes">
          <p>Apply to {selectedPaths.length} file(s):</p>
          <ul>
            {#each editEntries as [field, change] (field)}
              <li>
                {getFieldLabel(field)}:
                {#if change.action === "delete"}
                  <em>remove</em>
                {:else}
                  “{change.value}”
                {/if}
              </li>
            {/each}
          </ul>
          <div class="confirm-actions">
            <button
              type="button"
              class="primary"
              onclick={applyChanges}
              disabled={!canApply}
            >
              {saving ? "Saving…" : "Confirm"}
            </button>
            <button
              type="button"
              onclick={() => (confirming = false)}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </div>
      {:else}
        <button type="submit" class="primary apply" disabled={!canApply}>
          Apply to {selectedPaths.length} file(s)
        </button>
      {/if}
    </form>
  {/if}
</div>

<style>
  .bulk-editor {
    height: 100%;
    overflow-y: auto;
    padding: 16px;
    box-sizing: border-box;
    font-size: 14px;
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .selection-count,
  .note,
  .empty {
    color: #888;
  }
  .note.warning {
    color: #d84315;
  }
  .file-list {
    max-height: 240px;
    overflow-y: auto;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 4px 8px;
    margin-bottom: 16px;
  }
  .file-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    cursor: pointer;
    user-select: none;
  }
  .select-all {
    font-weight: 600;
    border-bottom: 1px solid #eee;
    padding-bottom: 6px;
    margin-bottom: 2px;
  }
  .file-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .field-row {
    display: grid;
    grid-template-columns: minmax(90px, 140px) 1fr auto;
    gap: 8px;
    align-items: center;
  }
  .field-row input {
    min-width: 0;
    padding: 5px 8px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 14px;
  }
  .field-row.changed input {
    border-color: var(--color-primary);
  }
  .field-row.deleted label {
    text-decoration: line-through;
  }
  .field-error {
    margin: -4px 0 0;
    color: #d32f2f;
    font-size: 13px;
  }
  button {
    background: transparent;
    border: 1px solid var(--color-primary);
    color: var(--color-primary);
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
  }
  button:hover:not(:disabled) {
    background: var(--color-primary-transparent);
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button.primary {
    background: var(--color-primary);
    color: #fff;
  }
  button.primary:hover:not(:disabled) {
    background: var(--color-primary-focus);
  }
  .apply {
    align-self: flex-start;
    margin-top: 8px;
  }
  .confirm {
    margin-top: 8px;
    padding: 12px;
    border: 1px solid var(--color-primary);
    border-radius: 4px;
    background: var(--color-primary-transparent);
  }
  .confirm p {
    margin: 0 0 6px;
    font-weight: 600;
  }
  .confirm ul {
    margin: 0 0 10px 18px;
    padding: 0;
  }
  .confirm-actions {
    display: flex;
    gap: 8px;
  }

  /* Dark mode */
  :global(body.dark) .file-list {
    border-color: #444;
  }
  :global(body.dark) .select-all {
    border-color: #444;
  }
  :global(body.dark) .field-row input {
    background: #2a2a2a;
    color: #e0e0e0;
    border-color: #555;
  }
  :global(body.dark) .field-row.changed input {
    border-color: var(--color-primary-dark);
  }
  :global(body.dark) .note.warning {
    color: #ff8a65;
  }
  :global(body.dark) button {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }
  :global(body.dark) button:hover:not(:disabled) {
    background: var(--color-primary-transparent-dark);
  }
  :global(body.dark) button.primary {
    background: var(--color-primary-dark);
    color: #1e1e1e;
  }
  :global(body.dark) .confirm {
    border-color: var(--color-primary-dark);
    background: var(--color-primary-transparent-dark);
  }
</style>
