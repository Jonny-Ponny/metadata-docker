<!-- src/components/Toast.svelte -->

<!-- Usage examples:

// Success
toast.success("File loaded successfully!");

// Error
toast.error("Failed to save tags");

// Warning
toast.warning("Please check your input");

// Info
toast.info("Loading file metadata...");

// Custom duration (10 seconds)
toast.show("This will stay longer", "info", 10000); -->

<script>
  import { onMount } from "svelte";

  let {
    message = "",
    type = "info",
    duration = 5000,
    onDismiss = () => {},
  } = $props();

  let visible = $state(true);
  let progress = $state(100);
  let timeoutId;
  let progressInterval;

  onMount(() => {
    // Auto-dismiss after duration
    timeoutId = setTimeout(() => {
      dismiss();
    }, duration);

    // Progress bar animation
    const startTime = Date.now();
    progressInterval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, duration - elapsed);
      progress = (remaining / duration) * 100;

      if (remaining <= 0) {
        clearInterval(progressInterval);
      }
    }, 50);

    return () => {
      clearTimeout(timeoutId);
      clearInterval(progressInterval);
    };
  });

  function dismiss() {
    visible = false;
    setTimeout(() => {
      onDismiss();
    }, 300);
  }

  // Type-based styling
  let toastClass = $derived(`toast toast-${type}`);
  let progressClass = $derived(`toast-progress progress-${type}`);
</script>

{#if visible}
  <div class={toastClass} class:fade-out={!visible} role="alert">
    <div class="toast-content">
      <span class="toast-message">{message}</span>
      <button class="toast-close" onclick={dismiss} aria-label="Close">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
    <div class={progressClass} style="width: {progress}%;"></div>
  </div>
{/if}

<style>
  .toast {
    position: relative;
    min-width: 300px;
    max-width: 500px;
    margin-bottom: 10px;
    padding: 12px 16px;
    background: white;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    animation: slide-in 0.3s ease-out;
    overflow: hidden;
    border-left: 4px solid transparent;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    /* Add these properties to ensure proper layering and interaction */
    pointer-events: auto;
    z-index: 9999;
  }

  .toast.fade-out {
    animation: slide-out 0.3s ease-in forwards;
    /* Keep pointer events during fade out to prevent accidental clicks behind */
    pointer-events: auto;
  }

  @keyframes slide-in {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  @keyframes slide-out {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(100%);
      opacity: 0;
    }
  }

  /* Toast types - matching your app's color scheme */
  .toast-success {
    border-left-color: #10b981;
  }

  .toast-error {
    border-left-color: #ef4444;
  }

  .toast-warning {
    border-left-color: #f59e0b;
  }

  .toast-info {
    border-left-color: #3b82f6;
  }

  .toast-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    /* Ensure content is clickable */
    pointer-events: auto;
  }

  .toast-message {
    flex: 1;
    font-size: 14px;
    color: #333;
    word-break: break-word;
    font-weight: 500;
    /* Allow text selection but maintain clickability */
    user-select: text;
    pointer-events: auto;
  }

  .toast-close {
    background: transparent;
    border: none;
    padding: 4px;
    cursor: pointer;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    transition: all 0.15s;
    flex-shrink: 0;
    /* Ensure button is clickable */
    pointer-events: auto;
    position: relative;
    z-index: 10000;
  }

  .toast-close:hover {
    background-color: #f0f0f0;
    color: #000;
    transform: scale(1.1);
  }

  .toast-progress {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 3px;
    background: rgba(0, 0, 0, 0.1);
    transition: width 0.05s linear;
    /* Progress bar shouldn't block clicks */
    pointer-events: none;
  }

  .progress-success {
    background: #10b981;
  }

  .progress-error {
    background: #ef4444;
  }

  .progress-warning {
    background: #f59e0b;
  }

  .progress-info {
    background: #3b82f6;
  }

  /* Dark mode overrides */
  :global(body.dark) .toast {
    background: #2d2d2d;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  }

  :global(body.dark) .toast-message {
    color: #e0e0e0;
  }

  :global(body.dark) .toast-close {
    color: #b0b0b0;
  }

  :global(body.dark) .toast-close:hover {
    background-color: #3d3d3d;
    color: #e0e0e0;
  }

  /* Keep progress bar colors the same or adjust if needed */
  :global(body.dark) .progress-success {
    background: #10b981;
  }

  :global(body.dark) .progress-error {
    background: #ef4444;
  }

  :global(body.dark) .progress-warning {
    background: #f59e0b;
  }

  :global(body.dark) .progress-info {
    background: #3b82f6;
  }
</style>