<!-- src/App.svelte -->
<script>
  import ToastContainer from "./components/ToastContainer.svelte";
  
  import { 
    theme, 
    toast,
    toggleTheme,
  } from "./utils/index.js";
  
  import "./app.css";

  // ========== STATE VARIABLES ==========
  let isLoading = $state(false);

  // Panel states
  let selectedFolder = $state(null);
  let selectedFile = $state(null);

  // UI states
  let leftPanelWidth = $state(50); // percentage
  let isResizing = $state(false);

  // ========== RESIZE HANDLERS ==========
  function startResize(e) {
    isResizing = true;
    document.body.classList.add("resizing"); // Add class to body for global text selection prevention
    document.addEventListener("mousemove", handleResize);
    document.addEventListener("mouseup", stopResize);
  }

  function handleResize(e) {
    if (!isResizing) return;
    e.preventDefault(); // Prevent default behaviors

    const container = document.querySelector(".split-container");
    if (!container) return;

    const containerRect = container.getBoundingClientRect();
    let newWidth =
      ((e.clientX - containerRect.left) / containerRect.width) * 100;

    // Clamp between 20% and 80%
    newWidth = Math.min(80, Math.max(20, newWidth));
    leftPanelWidth = newWidth;
  }

  function stopResize() {
    isResizing = false;
    document.body.classList.remove("resizing");
    document.removeEventListener("mousemove", handleResize);
    document.removeEventListener("mouseup", stopResize);
  }

  // ========== CLEANUP ==========
  $effect(() => {
    return () => {
      document.body.classList.remove("resizing");
      document.removeEventListener("mousemove", handleResize);
      document.removeEventListener("mouseup", stopResize);
    };
  });
</script>

<div class="container">
  <!-- Theme switch toggle -->
  <button class="theme-toggle" onclick={toggleTheme}>
    {#if $theme === "light"}
      <span>Light</span>
    {:else}
      <span>Dark</span>
    {/if}
  </button>

  <!-- Toast notifications -->
  <ToastContainer />

  <!-- Main split layout -->
  <div class="split-container">
    <!-- Left Panel - Folder Navigation / File Selection -->
    <div class="panel left-panel" style="width: {leftPanelWidth}%;">
      <div class="panel-header">
        <h3>File Browser</h3>
        {#if isLoading}
          <div class="status">Loading...</div>
        {/if}
      </div>

      <div class="panel-content">
        <!-- TODO: Add folder navigation component -->
        <div class="empty-state">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"
            />
          </svg>
          <p>Select a folder to browse music files</p>
        </div>
      </div>
    </div>

    <!-- Resizer handle -->
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      role="separator"
      class="resizer {isResizing ? 'resizing' : ''}"
      onmousedown={startResize}
    ></div>

    <!-- Right Panel - Metadata Editing -->
    <div class="panel right-panel" style="width: {100 - leftPanelWidth}%;">
      <div class="panel-header">
        <h3>Metadata Editor</h3>
        {#if selectedFile}
          <span class="filename-badge">{selectedFile}</span>
        {/if}
      </div>

      <div class="panel-content">
        <!-- TODO: Add metadata editing components -->
        <div class="empty-state">
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
            <polyline points="10 9 9 9 8 9" />
          </svg>
          <p>Select a file to edit metadata</p>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Player component -->
<!-- <Player {audioFile} ontimeupdate={handleTimeUpdate} bind:this={playerComponent} /> -->
