<!-- src/components/UploadTray.svelte -->
<script>
  import {
    upload,
    cancel,
    retryFailed,
    dismiss,
    proceedAnyway,
    formatBytes,
    formatDuration,
  } from "../utils/index.js";

  let expanded = $state(false);

  let percent = $derived(
    $upload.totalBytes > 0
      ? Math.min(100, ($upload.doneBytes / $upload.totalBytes) * 100)
      : 0,
  );

  let remainingSeconds = $derived(
    $upload.bytesPerSecond > 0 && $upload.totalBytes > $upload.doneBytes
      ? ($upload.totalBytes - $upload.doneBytes) / $upload.bytesPerSecond
      : 0,
  );

  let retryableCount = $derived(
    $upload.failures.filter((failure) => failure.retryable).length,
  );

  let isRunning = $derived(
    $upload.phase === "running" || $upload.phase === "cancelling",
  );

  let isRefreshing = $derived($upload.phase === "refreshing");

  let isComplete = $derived(
    $upload.phase === "done" && $upload.failed === 0 && !$upload.message,
  );

  let isWarning = $derived(
    $upload.phase === "blocked" ||
      ($upload.phase === "done" &&
        Boolean($upload.message) &&
        !$upload.message.startsWith("Upload cancelled")),
  );

  let hasError = $derived(
    $upload.failed > 0 ||
      ($isWarning &&
        Boolean($upload.message) &&
        !$upload.message.startsWith("Everything") &&
        !$upload.message.startsWith("Nothing") &&
        !$upload.message.startsWith("No files")),
  );

  let title = $derived.by(() => {
    switch ($upload.phase) {
      case "preparing":
        return "Reading folder…";
      case "blocked":
        return "Not enough free space";
      case "running":
        return `Uploading ${percent.toFixed(0)}%`;
      case "cancelling":
        return "Cancelling…";
      case "refreshing":
        return "Refreshing library…";
      case "done":
        if ($upload.message && $upload.message.startsWith("Upload cancelled")) {
          return "Upload cancelled";
        }
        if ($upload.message && $upload.message.startsWith("Session expired")) {
          return "Upload stopped";
        }
        if ($upload.failed > 0) return "Upload finished with errors";
        return "Upload complete";
      default:
        return "";
    }
  });

  let subtitle = $derived.by(() => {
    if ($upload.phase === "preparing") {
      if ($upload.scanFiles > 0) {
        return `${$upload.scanFiles.toLocaleString()} files · ${formatBytes($upload.scanBytes)} found`;
      }
      return "Reading the dropped folder…";
    }
    if ($upload.phase === "blocked") return $upload.message;
    if ($upload.phase === "refreshing") {
      const parts = [`${$upload.doneFiles} files saved`];
      if ($upload.queued > 0) parts.push(`${$upload.queued} queued`);
      return parts.join(" · ");
    }
    if ($upload.phase === "done") {
      const parts = [];
      if ($upload.uploaded) parts.push(`${$upload.uploaded} uploaded`);
      if ($upload.skipped) parts.push(`${$upload.skipped} skipped`);
      if ($upload.failed) parts.push(`${$upload.failed} failed`);
      if (!parts.length) return $upload.message;
      if ($upload.message && $upload.failed === 0) parts.push($upload.message);
      return parts.join(" · ");
    }
    if ($upload.phase === "cancelling") {
      if ($upload.totalBytes === 0) return "Stopping the folder scan…";
      return `${formatBytes($upload.doneBytes)} of ${formatBytes($upload.totalBytes)} sent`;
    }

    const parts = [
      `${formatBytes($upload.doneBytes)} / ${formatBytes($upload.totalBytes)}`,
      `${$upload.doneFiles} / ${$upload.totalFiles} files`,
    ];
    if (remainingSeconds > 0) parts.push(`~${formatDuration(remainingSeconds)} left`);
    if ($upload.queued > 0) parts.push(`${$upload.queued} queued`);
    return parts.join(" · ");
  });

  // Hide a successful upload after a moment; failures stay until dismissed.
  $effect(() => {
    if ($upload.phase !== "done" || $upload.failures.length > 0) return;
    const timer = setTimeout(() => dismiss(), 10000);
    return () => clearTimeout(timer);
  });
</script>

{#if $upload.phase !== "idle"}
  <div
    class="upload-tray"
    class:expanded
    role="region"
    aria-label="Upload progress"
    aria-live={isRunning || $upload.phase === "preparing" ? "off" : "polite"}
  >
    <div class="tray-row">
      <span
        class="tray-icon"
        class:error={hasError}
        class:done={isComplete && !hasError}
        aria-hidden="true"
      >
        {#if isComplete && !hasError}
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        {:else if hasError || isWarning}
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="9" />
            <line x1="12" y1="8" x2="12" y2="13" />
            <line x1="12" y1="16.5" x2="12" y2="16.5" />
          </svg>
        {:else}
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 19V5" />
            <polyline points="5 12 12 5 19 12" />
          </svg>
        {/if}
      </span>

      <div class="tray-text">
        <div class="tray-title">{title}</div>
        <div class="tray-subtitle" title={$upload.message}>{subtitle}</div>
      </div>

      <div class="tray-actions">
        {#if $upload.phase === "blocked"}
          <button class="tray-btn primary" onclick={proceedAnyway}>
            Upload anyway
          </button>
          <button class="tray-btn" onclick={cancel}>Cancel</button>
        {:else if $upload.phase === "preparing"}
          <!-- Reading a large folder can take a while; let the user stop it
               before a single byte is sent. -->
          <button class="tray-btn" onclick={cancel}>Cancel</button>
        {:else if isRunning}
          <button class="tray-btn" onclick={cancel}>Cancel</button>
        {:else if isRefreshing}
          <button class="tray-btn" onclick={dismiss}>Hide</button>
        {:else if $upload.phase === "done"}
          {#if retryableCount > 0}
            <button class="tray-btn primary" onclick={retryFailed}>
              Retry {retryableCount}
            </button>
          {/if}
          <button class="tray-btn" onclick={dismiss}>Dismiss</button>
        {/if}

        {#if $upload.failures.length > 0}
          <button
            class="tray-toggle"
            onclick={() => (expanded = !expanded)}
            title={expanded ? "Hide details" : "Show details"}
            aria-expanded={expanded}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.75"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              {#if expanded}
                <polyline points="18 15 12 9 6 15" />
              {:else}
                <polyline points="6 9 12 15 18 9" />
              {/if}
            </svg>
          </button>
        {/if}
      </div>
    </div>

    {#if isRunning || isRefreshing || $upload.phase === "preparing"}
      <div class="tray-track">
        <div
          class="tray-fill"
          class:indeterminate={$upload.phase === "preparing" ||
            isRefreshing ||
            $upload.totalBytes === 0}
          style="width: {$upload.phase === 'preparing' || $upload.totalBytes === 0
            ? 100
            : percent}%"
        ></div>
      </div>
    {/if}

    {#if expanded && $upload.failures.length > 0}
      <div class="tray-details">
        {#each $upload.failures.slice(0, 50) as failure}
          <div class="tray-failure">
            <span class="tray-failure-name" title={failure.name}
              >{failure.name}</span
            >
            <span class="tray-failure-reason">{failure.reason}</span>
          </div>
        {/each}
        {#if $upload.failures.length > 50}
          <div class="tray-more">and {$upload.failures.length - 50} more…</div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .upload-tray {
    position: fixed;
    right: 16px;
    bottom: 112px;
    width: min(400px, calc(100vw - 32px));
    box-sizing: border-box;
    background: #fff;
    color: #333;
    border: 1px solid #e8e8e8;
    border-radius: 6px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.07);
    font-size: 13px;
    line-height: 1.4;
    z-index: 9998;
    overflow: hidden;
  }

  .tray-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 15px;
  }

  .tray-icon {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    color: #8c8c8c;
  }

  .tray-icon.done {
    color: #2e7d32;
  }

  .tray-icon.error {
    color: #c62828;
  }

  .tray-text {
    flex: 1;
    min-width: 0;
  }

  .tray-title {
    font-weight: 600;
    font-size: 13px;
    line-height: 1.3;
    color: #2f2f2f;
  }

  .tray-subtitle {
    margin-top: 2px;
    color: #8c8c8c;
    font-size: 12px;
    line-height: 1.35;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tray-actions {
    display: flex;
    align-items: center;
    gap: 2px;
    flex: none;
  }

  .tray-btn {
    padding: 4px 7px;
    border: none;
    border-radius: 3px;
    background: transparent;
    color: #7a7a7a;
    font-size: 12px;
    line-height: 1.4;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
    white-space: nowrap;
  }

  .tray-btn:hover {
    background: #f2f2f2;
    color: #444;
  }

  .tray-btn.primary {
    color: var(--color-primary);
  }

  .tray-btn.primary:hover {
    background: var(--color-primary-transparent);
    color: var(--color-primary);
  }

  .tray-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: none;
    border-radius: 3px;
    background: transparent;
    color: #a0a0a0;
    cursor: pointer;
  }

  .tray-toggle:hover {
    background: #f2f2f2;
    color: #555;
  }

  .tray-track {
    height: 2px;
    background: #f0f0f0;
    overflow: hidden;
  }

  .tray-fill {
    height: 100%;
    background: var(--color-primary);
    transition: width 0.18s linear;
  }

  .tray-fill.indeterminate {
    opacity: 0.4;
    animation: tray-pulse 1.2s ease-in-out infinite;
  }

  @keyframes tray-pulse {
    0%,
    100% {
      opacity: 0.2;
    }
    50% {
      opacity: 0.5;
    }
  }

  .tray-details {
    max-height: 180px;
    overflow-y: auto;
    border-top: 1px solid #f0f0f0;
    padding: 4px 15px 8px;
  }

  .tray-failure {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 5px 0;
    border-bottom: 1px solid #f4f4f4;
  }

  .tray-failure:last-child {
    border-bottom: none;
  }

  .tray-failure-name {
    font-size: 12px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tray-failure-reason {
    font-size: 11.5px;
    color: #c62828;
  }

  .tray-more {
    padding-top: 4px;
    font-size: 11.5px;
    color: #8c8c8c;
  }

  :global(body.dark) .upload-tray {
    background: #2a2a2a;
    color: #e0e0e0;
    border-color: #3d3d3d;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.4);
  }

  :global(body.dark) .tray-title {
    color: #e8e8e8;
  }

  :global(body.dark) .tray-subtitle {
    color: #9a9a9a;
  }

  :global(body.dark) .tray-icon {
    color: #9a9a9a;
  }

  :global(body.dark) .tray-icon.done {
    color: #81c784;
  }

  :global(body.dark) .tray-icon.error {
    color: #ef9a9a;
  }

  :global(body.dark) .tray-btn {
    color: #a8a8a8;
  }

  :global(body.dark) .tray-btn:hover {
    background: #3a3a3a;
    color: #e0e0e0;
  }

  :global(body.dark) .tray-btn.primary {
    color: var(--color-primary-dark);
  }

  :global(body.dark) .tray-btn.primary:hover {
    background: #3a3a3a;
    color: var(--color-primary-dark);
  }

  :global(body.dark) .tray-toggle {
    color: #8c8c8c;
  }

  :global(body.dark) .tray-toggle:hover {
    background: #3a3a3a;
    color: #e0e0e0;
  }

  :global(body.dark) .tray-track {
    background: #3a3a3a;
  }

  :global(body.dark) .tray-details {
    border-top-color: #3a3a3a;
  }

  :global(body.dark) .tray-failure {
    border-bottom-color: #363636;
  }

  :global(body.dark) .tray-failure-reason {
    color: #ef9a9a;
  }

  :global(body.dark) .tray-more {
    color: #9a9a9a;
  }
</style>
