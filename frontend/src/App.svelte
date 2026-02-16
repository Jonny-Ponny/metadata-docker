<!-- src/App.svelte -->
<script>
  import ToastContainer from "./components/ToastContainer.svelte";
  import TreeNode from "./components/TreeNode.svelte";

  import { theme, toast, toggleTheme } from "./utils/index.js";

  import "./app.css";

  // ========== STATE VARIABLES ==========
  let isLoading = $state(false);
  let treeData = $state([]); // Store the file tree
  let error = $state("");

  // Panel states
  let selectedFolder = $state(null);
  let selectedFile = $state(null);

  // Tree expansion state
  let expandedDirs = $state(new Set());

  // UI states
  let leftPanelWidth = $state(50); // percentage
  let isResizing = $state(false);

  // ========== LOAD FILE TREE ==========
  async function loadFileTree() {
    isLoading = true;
    error = "";
    try {
      const api_url = "http://localhost:5000/api/files"; // development
      // const api_url = "/api/files" // build

      const res = await fetch(api_url);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Server error ${res.status}: ${text.slice(0, 100)}`);
      }
      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        const text = await res.text();
        throw new Error(
          `Expected JSON but got ${contentType}: ${text.slice(0, 100)}`,
        );
      }
      treeData = await res.json();

      // Auto-expand root directories (optional)
      // treeData.forEach(item => {
      //   if (item.type === 'directory') {
      //     expandedDirs.add(item.path);
      //   }
      // });
      // expandedDirs = new Set(expandedDirs);
    } catch (e) {
      error = e.message;
      toast.error(`Failed to load files: ${error}`);
    } finally {
      isLoading = false;
    }
  }

  // ========== TREE HANDLERS ==========
  function toggleDir(path) {
    if (expandedDirs.has(path)) {
      expandedDirs.delete(path);
    } else {
      expandedDirs.add(path);
    }
    // Trigger reactivity
    expandedDirs = new Set(expandedDirs);
  }

  function selectFile(path) {
    selectedFile = path;
    selectedFolder = null; // Clear folder selection
    toast.success(`Selected: ${path}`);
  }

  // Function to handle folder selection
  function selectFolder(path) {
    selectedFolder = path;
    selectedFile = null; // Clear file selection
    // Show a toast
    toast.success(`Selected folder: ${path}`);
  }

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
    loadFileTree();
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
        <div class="header-actions">
          {#if isLoading}
            <div class="status loading-spinner">
              <svg
                width="16"
                height="16"
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
              Loading...
            </div>
          {/if}
          <button
            class="refresh-btn"
            onclick={loadFileTree}
            title="Refresh file tree"
          >
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
          </button>
        </div>
      </div>

      <div class="panel-content file-tree-panel">
        {#if isLoading && treeData.length === 0}
          <div class="empty-state">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            <p>Loading files...</p>
          </div>
        {:else if error}
          <div class="error-state">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <circle cx="12" cy="16" r="0.5" fill="currentColor" />
            </svg>
            <p>Failed to load files</p>
            <p class="error-details">{error}</p>
            <button class="retry-btn" onclick={loadFileTree}>Retry</button>
          </div>
        {:else}
          <div class="file-tree-container">
            {#if treeData.length === 0}
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
                <p>No music files found</p>
              </div>
            {:else}
              <ul class="file-tree">
                {#each treeData as item (item.path)}
                  <TreeNode
                    {item}
                    expanded={expandedDirs}
                    {toggleDir}
                    {selectFile}
                    selectFolder={selectFolder}              
                    selectedFolder={selectedFolder}           
                    selectedFile={selectedFile}                
                  />
                {/each}
              </ul>
            {/if}
          </div>
        {/if}
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
