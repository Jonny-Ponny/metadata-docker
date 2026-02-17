<!-- src/App.svelte -->
<script>
  import ToastContainer from "./components/ToastContainer.svelte";
  import TreeNode from "./components/TreeNode.svelte";
  import MetadataEditor from "./components/MetadataEditor.svelte";
  import Player from "./components/Player.svelte";

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

  // Player-related state variables
  let audioFile = $state(null);
  let currentTime = $state(0);
  let playerComponent; // Player component reference (not reactive)

  // ========== DRAG AND DROP STATE ==========
  let isDragging = $state(false);
  let dragCounter = $state(0); // To handle drag enter/leave on child elements
  let uploadOverallProgress = $state({
    total: 0,
    completed: 0,
    isActive: false,
  });
  let dragOverElement = $state(null); // Track which element is being hovered
  let isUploading = $state(false);
  let hoverTimer = null;

  // ========== DRAG AND DROP HANDLERS ==========
  function handleDragEnter(e) {
    e.preventDefault();
    e.stopPropagation();

    dragCounter++;
    if (dragCounter === 1) {
      isDragging = true;
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";

    const newTarget = e.target.closest("[data-folder-path], [data-file-path]");

    // Only act if the hovered element actually changed
    if (newTarget !== dragOverElement) {
      // Remove highlight from previous element
      if (dragOverElement) {
        dragOverElement.classList.remove("drag-target");
      }

      // Add highlight to new element
      if (newTarget) {
        newTarget.classList.add("drag-target");
      }
      dragOverElement = newTarget;

      // Reset the expansion timer whenever the target changes
      if (hoverTimer) {
        clearTimeout(hoverTimer);
        hoverTimer = null;
      }

      // If the new target is a folder and not already expanded, start a timer
      if (newTarget && newTarget.hasAttribute("data-folder-path")) {
        const folderPath = newTarget.dataset.folderPath;
        if (!expandedDirs.has(folderPath)) {
          hoverTimer = setTimeout(() => {
            toggleDir(folderPath); // Expand the folder
            hoverTimer = null;
          }, 1000); // 1 second delay
        }
      }
    }
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();

    // Clear the expansion timer
    if (hoverTimer) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }

    // Remove drag-target class when leaving
    if (dragOverElement) {
      dragOverElement.classList.remove("drag-target");
      dragOverElement = null;
    }

    dragCounter--;
    if (dragCounter === 0) {
      isDragging = false;
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();

    // Clear the expansion timer
    if (hoverTimer) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }

    if (isUploading) {
      toast.warning("Upload in progress. Please wait.");
      return;
    }

    // Remove drag-target class
    if (dragOverElement) {
      dragOverElement.classList.remove("drag-target");
      dragOverElement = null;
    }

    // Reset drag state
    dragCounter = 0;
    isDragging = false;

    const items = e.dataTransfer.items;
    const files = e.dataTransfer.files;

    if (items.length === 0 && files.length === 0) return;

    // Determine target folder path
    let targetPath = "";

    // Check if dropped on a folder element
    const dropTarget = e.target.closest("[data-folder-path]");
    if (dropTarget) {
      targetPath = dropTarget.dataset.folderPath;
    } else {
      // Check if dropped on a file element (use its parent folder)
      const fileTarget = e.target.closest("[data-file-path]");
      if (fileTarget) {
        targetPath = fileTarget.dataset.folderPath;
      }
    }

    // Handle dropped items
    handleDroppedItems(items, files, targetPath);
  }

  async function handleDroppedItems(items, files, targetPath) {
    if (isUploading) return; // double-check
    isUploading = true;
    try {
      // --- Count total files first ---
      let totalFiles = 0;
      if (items.length > 0) {
        for (let i = 0; i < items.length; i++) {
          const entry = items[i].webkitGetAsEntry?.();
          if (entry) {
            totalFiles += await countFilesInEntry(entry);
          }
        }
      } else if (files.length > 0) {
        // Fallback: count all files (including those with webkitRelativePath)
        totalFiles = files.length;
      }

      // Activate overall progress bar
      uploadOverallProgress = {
        total: totalFiles,
        completed: 0,
        isActive: true,
      };

      // --- Proceed with uploads ---
      const uploads = [];

      if (items.length > 0) {
        for (let i = 0; i < items.length; i++) {
          const entry = items[i].webkitGetAsEntry?.();
          if (entry) {
            if (entry.isDirectory) {
              uploads.push(uploadDirectory(entry, targetPath));
            } else {
              uploads.push(uploadFileEntry(entry, targetPath));
            }
          }
        }
      } else if (files.length > 0) {
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          if (file.webkitRelativePath) {
            const relativePath = file.webkitRelativePath;
            const pathParts = relativePath.split("/");
            const fileName = pathParts.pop();
            const folderPath = pathParts.join("/");
            const fullTargetPath = targetPath
              ? `${targetPath}/${folderPath}`
              : folderPath;
            uploads.push(uploadFile(file, fullTargetPath, fileName));
          } else {
            uploads.push(uploadFile(file, targetPath, file.name));
          }
        }
      }

      try {
        const results = (await Promise.all(uploads)).flat();
        const successCount = results.filter((r) => r && r.success).length;
        const failCount = results.filter((r) => r && !r.success).length;

        if (failCount === 0) {
          toast.success(`Successfully uploaded ${successCount} file(s)`);
        } else {
          toast.warning(
            `Uploaded ${successCount} file(s), ${failCount} failed`,
          );
        }

        await loadFileTree();
      } catch (error) {
        toast.error(`Upload failed: ${error.message}`);
        console.error("Upload error:", error);
      } finally {
        // Deactivate progress bar
        uploadOverallProgress.isActive = false;
      }
    } finally {
      isUploading = false;
      uploadOverallProgress.isActive = false;
    }
  }

  async function uploadDirectory(entry, parentPath) {
    const dirPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;

    // Create the directory on the server (skip if dirPath is empty)
    if (dirPath) {
      console.log("Creating directory:", dirPath);
      await createDirectory(dirPath);
    }

    return new Promise((resolve) => {
      const reader = entry.createReader();
      const uploadPromises = [];

      function readEntries() {
        reader.readEntries(async (entries) => {
          if (entries.length === 0) {
            // All entries processed – wait for all pending uploads
            const results = await Promise.all(uploadPromises);
            resolve(results.flat()); // Flatten nested arrays
          } else {
            for (const childEntry of entries) {
              if (childEntry.isDirectory) {
                uploadPromises.push(uploadDirectory(childEntry, dirPath));
              } else {
                uploadPromises.push(uploadFileEntry(childEntry, dirPath));
              }
            }
            // Continue reading next batch (required by FileSystem API)
            readEntries();
          }
        });
      }

      readEntries();
    });
  }

  async function uploadFileEntry(entry, targetPath) {
    // Convert entry.file() callback to a Promise
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    // Upload the file with the correct target path and original filename
    console.log("uploadFileEntry:", entry.name, "to", targetPath);
    return uploadFile(file, targetPath, file.name);
  }

  async function uploadFile(file, targetPath, originalFilename) {
    console.log("uploadFile:", file.name, "to", targetPath);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("targetPath", targetPath || "");
    formData.append("originalFilename", originalFilename || file.name);

    try {
      console.log("Sending fetch for", originalFilename);
      const api_url = "http://localhost:5000/api/upload"; // development
      // const api_url = "/api/upload"; // build
      const response = await fetch(api_url, {
        method: "POST",
        body: formData,
      });
      console.log("Received response", response.status, response.statusText);

      const contentType = response.headers.get("content-type");
      let result;
      if (contentType && contentType.includes("application/json")) {
        result = await response.json();
      } else {
        const text = await response.text();
        console.error("Non-JSON response:", text);
        throw new Error(
          `Server returned ${response.status}: ${text.slice(0, 100)}`,
        );
      }

      if (!response.ok) {
        throw new Error(result.error || "Upload failed");
      }

      console.log("Upload success:", originalFilename, result);
      return {
        success: true,
        file: originalFilename || file.name,
        path: result.path,
      };
    } catch (error) {
      console.error("Upload error:", error);
      toast.error(
        `Failed to upload ${originalFilename || file.name}: ${error.message}`,
      );
      return {
        success: false,
        file: originalFilename || file.name,
        error: error.message,
      };
    } finally {
      // Increment overall progress (success or fail)
      uploadOverallProgress.completed += 1;
    }
  }

  async function createDirectory(path) {
    const api_url = "http://localhost:5000/api/mkdir"; // development
    // const api_url = '/api/mkdir'; // build
    const response = await fetch(api_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to create directory ${path}: ${error}`);
    }
    return response.json();
  }

  // Count total files in a dropped entry (file or directory)
  async function countFilesInEntry(entry) {
    if (entry.isFile) return 1;
    // Directory: recursively count children
    let count = 0;
    const reader = entry.createReader();
    const entries = await new Promise((resolve) => {
      reader.readEntries(resolve);
    });
    for (const child of entries) {
      count += await countFilesInEntry(child);
    }
    return count;
  }

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

    loadAudioFile(path);
  }

  async function loadAudioFile(filePath) {
    try {
      // Clean up previous blob URL if any
      if (audioFile?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(audioFile.url);
      }

      const url = `http://localhost:5000/api/audio?path=${encodeURIComponent(filePath)}`; // development
      // const url = `/api/audio?path=${encodeURIComponent(filePath)}`; // build
      const response = await fetch(url);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Server returned ${response.status}: ${errorText.slice(0, 100)}`,
        );
      }

      const contentType = response.headers.get("content-type");
      if (!contentType || !contentType.startsWith("audio/")) {
        const text = await response.text();
        console.error(
          "Unexpected content type:",
          contentType,
          "Response preview:",
          text.slice(0, 200),
        );
        throw new Error(
          `Expected audio file but got ${contentType || "unknown"}`,
        );
      }

      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);

      audioFile = {
        url: blobUrl,
        name: filePath.split(/[\\/]/).pop() || filePath,
        originalName: filePath,
        type: blob.type,
      };
    } catch (err) {
      toast.error(`Failed to load audio file: ${err.message}`);
      console.error("loadAudioFile error:", err);
    }
  }

  // Function to handle folder selection
  function selectFolder(path) {
    selectedFolder = path;
    selectedFile = null; // Clear file selection
  }

  function handleTimeUpdate(time) {
    currentTime = time;
    // You can add additional logic here if needed
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

      if (audioFile?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(audioFile.url);
      }

      // Clean up hover timer
      if (hoverTimer) {
        clearTimeout(hoverTimer);
      }
    };
  });
</script>

<div
  role="region"
  class="container"
  ondragenter={handleDragEnter}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  ondrop={handleDrop}
  class:dragging={isDragging}
>
  <!-- Theme switch toggle -->
  <button class="theme-toggle" class:blurred={isDragging} onclick={toggleTheme}>
    {#if $theme === "light"}
      <span>Light</span>
    {:else}
      <span>Dark</span>
    {/if}
  </button>

  <!-- Overall upload progress bar -->
  {#if uploadOverallProgress.isActive}
    <div
      class="upload-progress-bar"
      style="width: {uploadOverallProgress.total > 0
        ? (uploadOverallProgress.completed / uploadOverallProgress.total) * 100
        : 0}%;"
    ></div>
  {/if}

  <!-- Toast notifications -->
  <ToastContainer />

  <!-- Main split layout -->
  <div class="split-container" class:blurred={isDragging}>
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
              <!-- Update TreeNode usage to pass folder path data attributes -->
              <ul class="file-tree">
                {#each treeData as item (item.path)}
                  <TreeNode
                    {item}
                    expanded={expandedDirs}
                    {toggleDir}
                    {selectFile}
                    {selectFolder}
                    {selectedFolder}
                    {selectedFile}
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

        {#if selectedFile}
          <MetadataEditor filePath={selectedFile} />
        {:else}
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
        {/if}
      </div>
    </div>
  </div>
</div>

<!-- Player component -->
<div class="player-wrapper" class:blurred={isDragging}>
  <Player
    {audioFile}
    ontimeupdate={handleTimeUpdate}
    bind:this={playerComponent}
  />
</div>
