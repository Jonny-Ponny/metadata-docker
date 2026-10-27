<!-- src/App.svelte -->
<script>
  import { onMount } from "svelte";
  import { SvelteSet } from "svelte/reactivity";

  import ToastContainer from "./components/ToastContainer.svelte";
  import TreeNode from "./components/TreeNode.svelte";
  import MetadataEditor from "./components/MetadataEditor.svelte";
  import Player from "./components/Player.svelte";
  import SortButton from "./components/SortButton.svelte";
  import ImageViewer from "./components/ImageViewer.svelte";
  import Login from "./components/Login.svelte";
  import HelpModal from "./components/HelpModal.svelte";
  import LogViewer from "./components/LogViewer.svelte";
  import SettingsModal from "./components/SettingsModal.svelte";
  import TextEditor from "./components/TextEditor.svelte";
  import FolderOverview from "./components/FolderOverview.svelte";
  import UploadTray from "./components/UploadTray.svelte";

  import {
    sortItems,
    sortConfig,
    theme,
    toast,
    toggleTheme,
    renamingPath,
    isAuthenticated,
    initAuth,
    logout,
    getAuthHeaders,
    fetchVersionInfo,
    settings,
    applyThemeFromSettings,
    isAudioFile,
    readApiError,
    upload,
    startDrop,
    buildExistingIndex,
    loadUploadLimit,
  } from "./utils/index.js";

  import "./app.css";

  // Apply theme before any DOM updates
  $effect.pre(() => {
    applyThemeFromSettings($settings);
  });

  /**
   * @typedef {Object} TreeItem
   * @property {string} name
   * @property {string} path
   * @property {string} type
   * @property {string} [file_type]
   * @property {number} [size]
   * @property {TreeItem[]} [children]
   */

  /**
   * @typedef {Object} AudioFile
   * @property {string} url
   * @property {string} name
   * @property {string} originalName
   * @property {string} type
   */

  /**
   * The instance API Player exposes via `export`.
   * @typedef {Object} PlayerApi
   * @property {(time: number) => boolean} seekToTime
   * @property {() => void} stop
   * @property {() => number} getCurrentTime
   */

  /**
   * @typedef {Object} FolderAudioFile
   * @property {string} path
   * @property {string} name
   * @property {string} relativePath
   */

  // ========== STATE VARIABLES ==========
  let isLoading = $state(false);
  let treeData = $state(/** @type {TreeItem[]} */ ([])); // Store the file tree
  let error = $state("");
  // The authenticated effect loads the tree once. Without this guard an empty
  // library re-runs the effect on every `treeData = []`, looping /api/files.
  let treeRequested = false;

  // Panel states
  let selectedFolder = $state(/** @type {string | null} */ (null));
  let selectedFile = $state(/** @type {string | null} */ (null));

  // Tree expansion state
  let expandedDirs = new SvelteSet();

  // UI states
  let leftPanelWidth = $state(50); // percentage
  let isResizing = $state(false);

  // Player-related state variables
  let audioFile = $state(/** @type {AudioFile | null} */ (null));

  // svelte-ignore non_reactive_update
  /** @type {PlayerApi | undefined} */
  let playerComponent; // Player component reference (not reactive)

  // ========== DRAG AND DROP STATE ==========
  let isDragging = $state(false);
  // A tree item is being moved. Internal moves use pointer events instead of
  // the native HTML5 drag session: Firefox does not dispatch wheel events to
  // the page during a native drag, so the tree could not be scrolled with the
  // wheel while an item was held. A pointer-driven drag keeps normal input.
  let isInternalDrag = $state(false);
  let dragOverElement = $state(/** @type {HTMLElement | null} */ (null)); // Track which element is being hovered
  /** @type {ReturnType<typeof setTimeout> | null} */
  let hoverTimer = null;
  let folderInput = $state(/** @type {HTMLInputElement | null} */ (null));
  /** @type {{ path: string, type: "file" | "directory", name: string, startX: number, startY: number, pointerId: number } | null} */
  let pendingTreeDrag = null;
  /** @type {{ path: string, type: "file" | "directory", name: string } | null} */
  let draggedTreeItem = null;
  /** @type {HTMLElement | null} */
  let treeDragGhost = null;
  /** @type {HTMLElement | null} */
  let appContainer = $state(null);
  // Last pointer position during a tree drag, used by the edge auto-scroll
  // loop (the pointer can be still while the rows move under it).
  let dragPointerX = 0;
  let dragPointerY = 0;
  /** @type {number | null} */
  let dragAutoScrollFrame = null;
  // A drag ends with a click event from the browser; it must not select or
  // expand whatever happens to be under the pointer.
  let suppressTreeClick = false;

  // Upload state lives in the upload store. The flag is only used to warn
  // before closing the tab, since there is no resume yet.
  let isUploading = $derived(
    $upload.phase === "preparing" ||
      $upload.phase === "running" ||
      $upload.phase === "cancelling" ||
      $upload.phase === "blocked",
  );

  let uploadPercent = $derived(
    $upload.totalBytes > 0
      ? Math.min(100, ($upload.doneBytes / $upload.totalBytes) * 100)
      : 0,
  );

  let showProgressBar = $derived(
    $upload.phase === "preparing" ||
      $upload.phase === "running" ||
      $upload.phase === "cancelling" ||
      $upload.phase === "refreshing",
  );

  // Ref for the file tree container
  let fileTreeContainer = $state(/** @type {HTMLDivElement | null} */ (null));

  // ========== SEARCH STATE ==========
  let searchQuery = $state("");

  let showHelpModal = $state(false);

  let showLogViewer = $state(false);

  // First apply search filter, then sort
  let filteredTreeData = $derived(
    searchQuery && searchQuery.trim() !== ""
      ? filterTreeBySearch(treeData, searchQuery)
      : treeData,
  );

  // Derived store for sorted tree data
  let sortedTreeData = $derived(
    sortItems(filteredTreeData || [], $sortConfig.by, $sortConfig.direction),
  );

  let showSettingsModal = $state(false);

  // Version
  let currentVersion = $state(/** @type {string | null} */ (null));
  let gitSha = $state(/** @type {string | null} */ (null));

  let showFolderOverview = $state(false);

  let isTextDrag = $state(false);

  /**
   * @param {TreeItem} node
   * @returns {FolderAudioFile[]}
   */
  function collectAudioFilesRecursively(node) {
    /** @type {FolderAudioFile[]} */
    const result = [];
    const limit = 500; // safety limit

    /**
     * @param {TreeItem} currentNode
     * @param {string} [currentRelativePath]
     */
    function walk(currentNode, currentRelativePath = "") {
      if (result.length >= limit) return;

      if (currentNode.type === "file" && currentNode.file_type === "audio") {
        const relPath = currentRelativePath || currentNode.name;
        result.push({
          path: currentNode.path,
          name: currentNode.name,
          relativePath: relPath,
        });
      }

      if (currentNode.type === "directory" && currentNode.children) {
        for (const child of currentNode.children) {
          if (result.length >= limit) break;
          const childRelPath = currentRelativePath
            ? `${currentRelativePath}/${child.name}`
            : child.name;
          walk(child, childRelPath);
        }
      }
    }

    walk(node, "");
    return result;
  }

  /**
   * @returns {FolderAudioFile[]}
   */
  function getAudioFilesInFolder() {
    if (!selectedFolder) return [];

    /**
     * @param {TreeItem[]} nodes
     * @param {string} path
     * @returns {TreeItem | null}
     */
    function findNode(nodes, path) {
      for (const node of nodes) {
        if (node.path === path) return node;
        if (node.children) {
          const found = findNode(node.children, path);
          if (found) return found;
        }
      }
      return null;
    }

    const folderNode = findNode(treeData, selectedFolder);
    if (!folderNode) return [];

    if ($settings.recursiveOverview) {
      const files = collectAudioFilesRecursively(folderNode);
      if (files.length >= 500) {
        toast.warning(
          "Folder overview limited to 500 files. Some subfolders may be incomplete.",
        );
      }
      return files;
    }

    // Non‑recursive: direct children only, relativePath is just the filename
    return (folderNode.children ?? [])
      .filter((child) => child.type === "file" && child.file_type === "audio")
      .map((child) => ({
        path: child.path,
        name: child.name,
        relativePath: child.name,
      }));
  }

  let audioFilesInFolder = $derived(getAudioFilesInFolder());

  // ========== DRAG AND DROP HANDLERS ==========
  // Only `dragenter` arms the overlay; `dragover` merely keeps an active drag
  // alive. Firefox does not always deliver a balanced dragenter/dragleave pair
  // and does not send dragend for drags that started outside the page, so
  // counting leaves used to leave `isDragging` on forever (and a stray
  // dragover kept re-arming it). Every terminal signal (drop, dragend, blur,
  // Esc, a pointer event) clears it outright, and a watchdog clears it if
  // dragover stops.
  /** @type {ReturnType<typeof setInterval> | null} */
  let dragWatchdog = null;
  let lastDragOverAt = 0;
  // Set right after a drop: Firefox can deliver stray dragenter/dragover
  // events *after* the drop (notably when the drop target is a folder row),
  // which re-armed the overlay that had just been cleared.
  let dropGuardUntil = 0;

  // `DataTransfer.types` is an array in current browsers but was a
  // DOMStringList (with `contains`, not `includes`) in older Firefox. Never
  // throw here: an exception in a drag handler skips the state reset and is
  // exactly how the blur used to get stuck.
  /**
   * @param {any} types
   * @param {string} type
   * @returns {boolean}
   */
  function hasType(types, type) {
    if (!types) return false;
    if (typeof types.includes === "function") return types.includes(type);
    if (typeof types.contains === "function") return types.contains(type);
    return Array.from(types).includes(type);
  }

  /**
   * @param {DragEvent} e
   * @returns {boolean}
   */
  function hasFiles(e) {
    return hasType(e?.dataTransfer?.types, "Files");
  }

  function resetDragState() {
    isDragging = false;
    isInternalDrag = false;
    pendingTreeDrag = null;
    draggedTreeItem = null;
    stopTreeAutoScroll();

    if (hoverTimer) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }

    if (dragOverElement) {
      dragOverElement.classList.remove("drag-target");
      dragOverElement = null;
    }

    if (treeDragGhost) {
      treeDragGhost.remove();
      treeDragGhost = null;
    }
    if (typeof document !== "undefined") {
      document.body.classList.remove("internal-dragging");
    }

    if (dragWatchdog) {
      clearInterval(dragWatchdog);
      dragWatchdog = null;
    }
  }

  function startDragWatchdog() {
    if (dragWatchdog) return;
    dragWatchdog = setInterval(() => {
      // dragover is repeated every few hundred milliseconds while a drag is
      // actually over the page; if it stops, the drag was dropped elsewhere,
      // cancelled or left the window.
      if (Date.now() - lastDragOverAt > 1500) resetDragState();
    }, 300);
  }

  // The current drag has ended. The short guard keeps late drag events from
  // the browser from switching the overlay back on.
  function endDrag() {
    dropGuardUntil = Date.now() + 1000;
    resetDragState();
  }

  /**
   * @param {DragEvent} e
   */
  function handleDragEnter(e) {
    if (isTextDrag) return;
    if (!hasFiles(e)) return;

    e.preventDefault();
    e.stopPropagation();

    // A stray enter right after a drop must not re-arm the overlay. The drop
    // itself is still allowed (see handleDragOver).
    if (Date.now() < dropGuardUntil) return;
    if (isDragging) return;

    lastDragOverAt = Date.now();
    isDragging = true;
    startDragWatchdog();
  }

  /**
   * Highlight the node under a drag and expand a hovered folder after a short
   * dwell. Shared by native file drags and the pointer-driven tree drag.
   * @param {HTMLElement | null} newTarget
   */
  function setDragTarget(newTarget) {
    if (newTarget === dragOverElement) return;

    if (dragOverElement) {
      dragOverElement.classList.remove("drag-target");
    }
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
      if (folderPath && !expandedDirs.has(folderPath)) {
        hoverTimer = setTimeout(() => {
          toggleDir(folderPath); // Expand the folder
          hoverTimer = null;
        }, 1000); // 1 second delay
      }
    }
  }

  /**
   * @param {DragEvent} e
   */
  function handleDragOver(e) {
    if (isTextDrag) return;

    // Native drags are only external files now; tree moves are pointer-driven.
    if (!hasFiles(e)) return;

    e.preventDefault();
    e.stopPropagation();

    if (isDragging) {
      // dragover keeps the active drag alive; it must never *arm* the
      // overlay, or a stray event after the drag ended re-blurs the app.
      lastDragOverAt = Date.now();
    }

    const eventTarget = e.target instanceof Element ? e.target : null;
    /** @type {HTMLElement | null} */
    const newTarget =
      eventTarget?.closest("[data-folder-path], [data-file-path]") ?? null;
    setDragTarget(newTarget);
  }

  /**
   * @param {DragEvent} e
   */
  function handleDragLeave(e) {
    if (isTextDrag) return;
    e.preventDefault();
    e.stopPropagation();

    // Firefox sends dragleave when the pointer merely moves between child
    // elements, so a leave event is only terminal when the pointer is outside
    // the viewport. Everything else is caught by the drop/pointer handlers or
    // the watchdog.
    const leftWindow =
      e.clientX < 0 ||
      e.clientY < 0 ||
      e.clientX >= window.innerWidth ||
      e.clientY >= window.innerHeight;

    if (leftWindow) endDrag();
  }

  /**
   * Scroll the file tree with the wheel while one of its items is being
   * dragged. The pointer-driven drag keeps normal input, but the wheel may be
   * targeted at the ghost, the panel header or the window rather than the
   * scrolling panel. The window-level capture listener keeps the tree
   * scrolling from wherever the pointer is and prevents the page behind it
   * from scrolling instead.
   * @param {WheelEvent} event
   */
  function handleTreeWheel(event) {
    if (!isInternalDrag || !fileTreeContainer) return;
    // Do not swallow the wheel for the rest of the page when there is nothing
    // to scroll (a short tree, or a horizontal-only wheel).
    if (fileTreeContainer.scrollHeight <= fileTreeContainer.clientHeight) {
      return;
    }
    if (event.deltaY === 0) return;

    event.preventDefault();
    // deltaY is in lines or pages with these deltaMode values, not pixels.
    const step =
      event.deltaMode === 1
        ? 16
        : event.deltaMode === 2
          ? fileTreeContainer.clientHeight
          : 1;
    fileTreeContainer.scrollTop += event.deltaY * step;
  }

  /**
   * The tree node under a point on the page.
   * @param {number} x
   * @param {number} y
   * @returns {HTMLElement | null}
   */
  function treeNodeAtPoint(x, y) {
    if (typeof document.elementFromPoint !== "function") return null;
    const element = document.elementFromPoint(x, y);
    return element instanceof Element
      ? /** @type {HTMLElement | null} */ (
          element.closest("[data-folder-path], [data-file-path]")
        )
      : null;
  }

  /**
   * The tree node under a pointer event. Pointer events already target the
   * element under the cursor, so `event.target` is normally enough; the
   * geometry lookup keeps this working when the target is the window (tests,
   * or a synthetic event).
   * @param {PointerEvent} event
   * @returns {HTMLElement | null}
   */
  function treeNodeAt(event) {
    if (event.target instanceof Element) {
      const direct = event.target.closest(
        "[data-folder-path], [data-file-path]",
      );
      if (direct) return /** @type {HTMLElement} */ (direct);
    }
    return treeNodeAtPoint(event.clientX, event.clientY);
  }

  function stopTreeAutoScroll() {
    if (dragAutoScrollFrame !== null) {
      cancelAnimationFrame(dragAutoScrollFrame);
      dragAutoScrollFrame = null;
    }
  }

  /**
   * Scroll the tree while a dragged item is held near its top or bottom edge.
   * The native drag used to do this itself; a pointer drag has to implement it.
   * The loop keeps running while the pointer is still so the rows keep moving,
   * and re-evaluates the drop target because the content moves underneath it.
   */
  function treeAutoScrollStep() {
    dragAutoScrollFrame = null;
    if (!isInternalDrag || !fileTreeContainer) return;

    const rect = fileTreeContainer.getBoundingClientRect();
    if (
      dragPointerX < rect.left ||
      dragPointerX > rect.right ||
      dragPointerY < rect.top ||
      dragPointerY > rect.bottom
    ) {
      return;
    }

    const edge = Math.min(40, rect.height / 4);
    /** @type {number} */
    let speed = 0;
    if (dragPointerY < rect.top + edge) {
      speed = -18 * ((rect.top + edge - dragPointerY) / edge);
    } else if (dragPointerY > rect.bottom - edge) {
      speed = 18 * ((dragPointerY - (rect.bottom - edge)) / edge);
    }
    if (speed === 0) return;

    const maxScroll =
      fileTreeContainer.scrollHeight - fileTreeContainer.clientHeight;
    if (maxScroll <= 0) return;

    const previous = fileTreeContainer.scrollTop;
    const next = Math.min(maxScroll, Math.max(0, previous + speed));
    if (next === previous) return;
    fileTreeContainer.scrollTop = next;

    setDragTarget(treeNodeAtPoint(dragPointerX, dragPointerY));
    dragAutoScrollFrame = requestAnimationFrame(treeAutoScrollStep);
  }

  function scheduleTreeAutoScroll() {
    if (
      dragAutoScrollFrame !== null ||
      !isInternalDrag ||
      typeof requestAnimationFrame !== "function"
    ) {
      return;
    }
    dragAutoScrollFrame = requestAnimationFrame(treeAutoScrollStep);
  }

  /**
   * Arm a pointer-driven move when a tree row is pressed. The drag only starts
   * after a few pixels of movement so normal clicks keep working.
   * @param {PointerEvent} event
   */
  function handleTreePointerDown(event) {
    if (event.button !== 0 || event.pointerType === "touch") return;
    // A new press starts a new interaction; any pending click suppression is
    // stale by now.
    suppressTreeClick = false;

    if (
      event.target instanceof Element &&
      event.target.closest("input, textarea, button, [contenteditable='true']")
    ) {
      return;
    }

    const node = treeNodeAt(event);
    if (!node) return;
    const path =
      node.getAttribute("data-file-path") ??
      node.getAttribute("data-folder-path");
    if (!path) return;
    // TreeNode shows an input instead of the label while renaming; the row
    // must not turn into a drag target then.
    if ($renamingPath === path) return;

    pendingTreeDrag = {
      path,
      type: node.hasAttribute("data-file-path") ? "file" : "directory",
      name: path.split("/").pop() ?? path,
      startX: event.clientX,
      startY: event.clientY,
      pointerId: event.pointerId,
    };
  }

  /**
   * @param {PointerEvent} event
   */
  function beginTreeDrag(event) {
    if (!pendingTreeDrag) return;
    draggedTreeItem = {
      path: pendingTreeDrag.path,
      type: pendingTreeDrag.type,
      name: pendingTreeDrag.name,
    };
    pendingTreeDrag = null;
    isInternalDrag = true;
    dragPointerX = event.clientX;
    dragPointerY = event.clientY;

    document.body.classList.add("internal-dragging");
    document.getSelection()?.removeAllRanges();

    const ghost = document.createElement("div");
    ghost.className = "tree-drag-ghost";
    ghost.textContent = draggedTreeItem.name;
    ghost.style.left = `${event.clientX}px`;
    ghost.style.top = `${event.clientY}px`;
    document.body.appendChild(ghost);
    treeDragGhost = ghost;

    setDragTarget(treeNodeAt(event));
    scheduleTreeAutoScroll();
  }

  /**
   * @param {PointerEvent} event
   */
  function handleTreePointerMove(event) {
    if (!pendingTreeDrag && !isInternalDrag) return;

    if (!isInternalDrag) {
      if (!pendingTreeDrag || pendingTreeDrag.pointerId !== event.pointerId) {
        return;
      }
      // Keep the browser from starting a text selection while the pointer is
      // held down, even before the drag threshold is crossed.
      event.preventDefault();
      const dx = event.clientX - pendingTreeDrag.startX;
      const dy = event.clientY - pendingTreeDrag.startY;
      if (dx * dx + dy * dy < 25) return;
      beginTreeDrag(event);
      return;
    }

    event.preventDefault();
    dragPointerX = event.clientX;
    dragPointerY = event.clientY;
    if (treeDragGhost) {
      treeDragGhost.style.left = `${event.clientX}px`;
      treeDragGhost.style.top = `${event.clientY}px`;
    }
    setDragTarget(treeNodeAt(event));
    scheduleTreeAutoScroll();
  }

  /**
   * @param {PointerEvent} event
   */
  function handleTreePointerUp(event) {
    pendingTreeDrag = null;
    if (!isInternalDrag) return;

    // The drag is over, so the browser's follow-up click must not select or
    // toggle whatever the item was dropped on.
    suppressTreeClick = true;

    const item = draggedTreeItem;
    const targetNode = treeNodeAt(event);
    const targetPath =
      targetNode?.getAttribute("data-file-path") ??
      targetNode?.getAttribute("data-folder-path") ??
      "";
    const targetFolder = targetNode?.getAttribute("data-folder-path") ?? "";
    // The old native drop moved an item to the library root whenever it was
    // released outside a tree row, including the File Browser header. Keep
    // that: the only real cancel is a release outside the app window.
    const insideApp =
      !!appContainer &&
      event.target instanceof Node &&
      appContainer.contains(event.target);

    resetDragState();

    if (!item) return;
    if (!targetNode && !insideApp) return;

    // Dropped directly on itself (a file row or its own folder row).
    if (targetPath === item.path) {
      toast.warning("Cannot move an item into itself");
      return;
    }

    if (item.type === "directory") {
      if (targetFolder.startsWith(`${item.path}/`)) {
        toast.warning("Cannot move a folder into its own subfolder");
        return;
      }
    }

    // Dropping an item beside itself is a no-op rather than an API round trip.
    const parent = item.path.includes("/")
      ? item.path.slice(0, item.path.lastIndexOf("/"))
      : "";
    if (targetFolder === parent) return;

    handleMove(item.path, targetFolder);
  }

  function handleTreePointerCancel() {
    pendingTreeDrag = null;
    if (isInternalDrag) resetDragState();
  }

  /**
   * @param {DragEvent} e
   */
  function handleDrop(e) {
    // End the drag state before anything else: the rest of this handler can
    // throw (missing DataTransfer, unreadable entries) and a stuck blur is
    // far worse than a dropped upload.
    resetDragState();

    if (isTextDrag) return;
    e.preventDefault();
    e.stopPropagation();

    // Native drops are external uploads; tree moves end in handleTreePointerUp.
    if (!hasFiles(e)) return;

    // --- External upload ---
    const items = Array.from(e.dataTransfer?.items ?? []);
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (!items.length && !files.length) return;

    // Determine the target folder: the hovered folder, the parent folder of a
    // hovered file, or the library root.
    let targetPath = "";
    const eventTarget = e.target instanceof Element ? e.target : null;
    /** @type {HTMLElement | null} */
    const dropTarget = eventTarget?.closest("[data-folder-path]") ?? null;
    if (dropTarget) {
      targetPath = dropTarget.dataset.folderPath ?? "";
    } else {
      /** @type {HTMLElement | null} */
      const fileTarget = eventTarget?.closest("[data-file-path]") ?? null;
      if (fileTarget) {
        targetPath = fileTarget.dataset.folderPath ?? "";
      }
    }

    // webkitGetAsEntry() is only valid while the drop event is still being
    // dispatched, so resolve the entries before handing off to the async
    // upload queue.
    const entries = items
      .map((item) => {
        try {
          return item.webkitGetAsEntry?.();
        } catch {
          return null;
        }
      })
      .filter((entry) => entry !== null);

    startDrop({
      entries,
      files,
      targetPath,
      existing: buildExistingIndex(treeData),
      conflict: $settings.uploadDuplicates || "skip-identical",
      onComplete: loadFileTree,
    }).catch((error) => {
      console.error("Upload failed:", error);
      toast.error(
        `Upload failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    });
  }

  /**
   * @param {Event} event
   */
  async function handleFolderInput(event) {
    const input = /** @type {HTMLInputElement} */ (event.target);
    const files = Array.from(input.files || []);
    input.value = ""; // allow picking the same folder twice
    if (!files.length) return;

    startDrop({
      files,
      targetPath: selectedFolder || "",
      existing: buildExistingIndex(treeData),
      conflict: $settings.uploadDuplicates || "skip-identical",
      onComplete: loadFileTree,
    }).catch((error) => {
      console.error("Upload failed:", error);
      toast.error(
        `Upload failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    });
  }

  // ========== LOAD FILE TREE ==========
  async function loadFileTree() {
    isLoading = true;
    error = "";
    try {
      const api_url = "/api/files"; // build
      const res = await fetch(api_url);
      if (!res.ok) {
        throw new Error(
          await readApiError(res, "Could not load the file tree"),
        );
      }
      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        throw new Error(
          `Expected a JSON response but received ${contentType || "an unknown content type"}`,
        );
      }
      treeData = await res.json();

      // Initial sort will be applied by the TreeNode components via the store
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      toast.error(`Failed to load files: ${error}`);
    } finally {
      isLoading = false;
    }
  }

  // ========== TREE HANDLERS ==========
  /**
   * @param {string} path
   */
  function toggleDir(path) {
    if (expandedDirs.has(path)) {
      expandedDirs.delete(path);
    } else {
      expandedDirs.add(path);
    }
  }

  /**
   * @param {string} path
   */
  function selectFile(path) {
    selectedFile = path;
    selectedFolder = null;
  }

  /**
   * @param {string} filePath
   */
  async function loadAudioFile(filePath) {
    try {
      // Clean up previous blob URL if any
      if (audioFile?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(audioFile.url);
      }

      const url = `/api/audio?path=${encodeURIComponent(filePath)}`; // build
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(
          await readApiError(response, "Could not load the audio file"),
        );
      }

      const contentType = response.headers.get("content-type");
      if (!contentType || !contentType.startsWith("audio/")) {
        console.error("Unexpected audio content type:", contentType);
        throw new Error(
          `Expected an audio file but received ${contentType || "an unknown content type"}`,
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
      toast.error(
        `Failed to load audio file: ${err instanceof Error ? err.message : String(err)}`,
      );
      console.error("loadAudioFile error:", err);
    }
  }

  // Function to handle folder selection
  /**
   * @param {string} path
   */
  function selectFolder(path) {
    selectedFolder = path;
    selectedFile = null;
  }

  // ========== RESIZE HANDLERS ==========
  function startResize() {
    isResizing = true;
    document.body.classList.add("resizing"); // Add class to body for global text selection prevention
    document.addEventListener("mousemove", handleResize);
    document.addEventListener("mouseup", stopResize);
  }

  /**
   * @param {MouseEvent} e
   */
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

  // Keydown
  /**
   * @param {KeyboardEvent} e
   */
  function handleKeyDown(e) {
    // Check if we're in a rename operation
    if ($renamingPath) {
      // Let the rename input handle the keys
      return;
    }

    // Check if any input, textarea, or contenteditable is focused
    const activeElement = document.activeElement;
    const isInputFocused =
      activeElement &&
      (activeElement.tagName === "INPUT" ||
        activeElement.tagName === "TEXTAREA" ||
        activeElement.getAttribute("contenteditable") === "true" ||
        activeElement.closest(".modal-content") !== null || // Any modal content
        activeElement.closest(".timestamp-input") !== null || // Timestamp editor
        activeElement.closest(".edit-textarea") !== null); // Edit modal textarea

    if (isInputFocused) {
      // Don't handle keyboard shortcuts when user is typing
      return;
    }

    if (e.key === "F2" && selectedFile) {
      e.preventDefault();
      renamingPath.set(selectedFile);
    } else if (e.key === "F2" && selectedFolder) {
      e.preventDefault();
      renamingPath.set(selectedFolder);
    }

    if ($settings.allowDeleteKey) {
      if (e.key === "Delete" && selectedFile) {
        e.preventDefault();
        handleDelete(selectedFile);
      } else if (e.key === "Delete" && selectedFolder) {
        e.preventDefault();
        handleDelete(selectedFolder);
      }
    }
  }

  // ========== CLEANUP ==========
  $effect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.classList.remove("resizing");
      document.removeEventListener("mousemove", handleResize);
      document.removeEventListener("mouseup", stopResize);

      if (audioFile?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(audioFile.url);
      }

      window.removeEventListener("keydown", handleKeyDown);

      // Clean up hover timer
      if (hoverTimer) {
        clearTimeout(hoverTimer);
      }
    };
  });

  // ========== RENAME & DELETE HANDLERS ==========
  /**
   * @param {string} oldPath
   * @param {string} newName
   */
  async function handleRename(oldPath, newName) {
    try {
      const api_url = "/api/rename"; // build
      const res = await fetch(api_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ oldPath, newName }),
      });
      if (!res.ok) {
        throw new Error(await readApiError(res));
      }
      const data = await res.json();

      // Update expanded directories if the renamed item was expanded
      if (expandedDirs.has(oldPath)) {
        expandedDirs.delete(oldPath);
        expandedDirs.add(data.newPath);
      }

      // Update selected item if it was renamed
      if (selectedFolder === oldPath) selectedFolder = data.newPath;
      if (selectedFile === oldPath) selectedFile = data.newPath;

      // Reload tree to reflect changes (simple but loses child expansions)
      await loadFileTree();
      toast.success("Renamed successfully");
    } catch (e) {
      toast.error(
        `Rename failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  }

  /**
   * @param {string} path
   */
  async function handleDelete(path) {
    try {
      const api_url = "/api/delete"; // build
      const res = await fetch(api_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) {
        throw new Error(await readApiError(res));
      }

      // Clear selection if the deleted item was selected
      if (selectedFolder === path) selectedFolder = null;
      if (selectedFile === path) selectedFile = null;

      // Remove from expanded set if it was a directory
      if (expandedDirs.has(path)) {
        expandedDirs.delete(path);
      }

      await loadFileTree();
      toast.success("Deleted successfully");
    } catch (e) {
      toast.error(
        `Delete failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  }

  /**
   * @param {string} sourcePath
   * @param {string} destFolderPath
   */
  async function handleMove(sourcePath, destFolderPath) {
    try {
      const api_url = "/api/move"; // build
      const res = await fetch(api_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: sourcePath,
          destination: destFolderPath,
        }),
      });
      if (!res.ok) {
        throw new Error(await readApiError(res));
      }
      toast.success("Moved successfully");
      // Reload tree to reflect changes
      await loadFileTree();
    } catch (e) {
      toast.error(`Move failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  /**
   * @param {string} parentPath
   * @param {string} [baseName]
   */
  async function handleCreateFolder(parentPath, baseName = "New Folder") {
    try {
      const desiredPath = parentPath ? `${parentPath}/${baseName}` : baseName;
      const api_url = "/api/mkdir"; // build

      const res = await fetch(api_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: desiredPath }),
      });

      if (!res.ok) {
        throw new Error(await readApiError(res));
      }

      const data = await res.json();

      // If creating inside a folder, make sure that parent is expanded
      if (parentPath) {
        expandedDirs.add(parentPath);
      }

      // Select the newly created folder
      selectedFolder = data.path; // or desiredPath if API doesn't return path
      selectedFile = null;

      toast.success(`Folder created: ${data.path}`);
      await loadFileTree(); // refresh the tree to show the new folder
    } catch (e) {
      toast.error(
        `Create folder failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  }

  /**
   * @param {string} path
   */
  async function handleCopyItem(path) {
    try {
      const api_url = "/api/copy"; // build
      const res = await fetch(api_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) {
        throw new Error(await readApiError(res));
      }

      // Clear selection if the item was selected
      if (selectedFolder === path) selectedFolder = null;
      if (selectedFile === path) selectedFile = null;

      await loadFileTree();
      toast.success("Copied successfully");
    } catch (e) {
      toast.error(`Copy failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // Function to scroll selected item into view
  function scrollSelectedIntoView() {
    if (!selectedFile && !selectedFolder) return;

    const selectedPath = selectedFile || selectedFolder;

    // Use a combination of techniques
    const tryScroll = (attempt = 0) => {
      if (attempt > 5) return; // Max 5 attempts

      const selector = selectedFile
        ? `[data-file-path="${selectedPath}"]`
        : `[data-folder-path="${selectedPath}"]`;

      const element = document.querySelector(selector);

      if (element && fileTreeContainer) {
        // Force scroll regardless of position
        element.scrollIntoView({
          block: "center",
          inline: "nearest",
        });
      } else {
        // Element not found yet, try again
        setTimeout(() => tryScroll(attempt + 1), 50 * (attempt + 1));
      }
    };

    // Start trying
    setTimeout(() => tryScroll(), 50);
  }

  // Watch for sort config changes
  $effect(() => {
    if ($sortConfig) {
      // When sort changes, scroll selected item into view
      scrollSelectedIntoView();
    }
  });

  // Also watch for selection changes
  $effect(() => {
    if (selectedFile || selectedFolder) {
      scrollSelectedIntoView();
    }
  });

  // Watch for tree data changes (after refresh, upload, etc.)
  $effect(() => {
    if (treeData.length > 0) {
      scrollSelectedIntoView();
    }
  });

  // ========== SEARCH FUNCTION ==========
  /**
   * @param {TreeItem[]} nodes
   * @param {string} query
   * @returns {TreeItem[] | null}
   */
  function filterTreeBySearch(nodes, query) {
    if (!query || query.trim() === "") return null;

    const lowerQuery = query.toLowerCase().trim();

    /**
     * @param {TreeItem} node
     * @returns {TreeItem | null}
     */
    function filterNode(node) {
      // Check if current node matches
      const nameMatch = node.name.toLowerCase().includes(lowerQuery);

      // For directories, check children
      if (node.type === "directory" && node.children) {
        const filteredChildren = node.children
          .map(filterNode)
          .filter((child) => child !== null);

        // Include directory if it matches OR has matching children
        if (nameMatch || filteredChildren.length > 0) {
          return {
            ...node,
            children:
              filteredChildren.length > 0 ? filteredChildren : node.children,
          };
        }
      }

      // For files or directories without matching children
      return nameMatch ? node : null;
    }

    return nodes.map(filterNode).filter((node) => node !== null);
  }

  // Logout handler
  function handleLogout() {
    logout();
  }

  async function checkVersion() {
    try {
      const data = await fetchVersionInfo();
      currentVersion = data.current_version;
      gitSha = data.git_sha || null;
      if (data.update_available) {
        toast.show(
          "Update available, check GitHub for more info",
          "info",
          10000,
        );
      }
    } catch (e) {
      console.warn("Version check failed:", e);
    }
  }

  /**
   * @param {DragEvent} e
   */
  function handleDocumentDragStart(e) {
    // Native drags are only external files or dragged text now; tree moves
    // are pointer-driven (see handleTreePointerDown), so no tree item needs
    // to be recognised here.
    const el = e.target instanceof HTMLElement ? e.target : null;
    isTextDrag = !!(
      el &&
      (el.tagName === "INPUT" ||
        el.tagName === "TEXTAREA" ||
        el.isContentEditable ||
        (el.closest && el.closest('input, textarea, [contenteditable="true"]')))
    );
  }

  function handleDocumentDragEnd() {
    isTextDrag = false;
    // An internal drag can be released anywhere; never leave the overlay on.
    endDrag();
  }

  onMount(() => {
    initAuth();

    // Add auth headers to all fetch requests
    const originalFetch = window.fetch;
    window.fetch = async (url, options = {}) => {
      const headers = getAuthHeaders();
      options.headers = {
        ...headers,
        ...options.headers,
      };

      const response = await originalFetch(url, options);

      // If unauthorized, logout
      if (response.status === 401) {
        logout();
      }

      return response;
    };

    window.addEventListener("refreshFileTree", loadFileTree);
    scrollSelectedIntoView();

    checkVersion();
    loadUploadLimit();

    // There is no resume yet, so warn before a reload drops the queue.
    /** @param {BeforeUnloadEvent} event */
    const handleBeforeUnload = (event) => {
      if (!isUploading) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    document.addEventListener("dragstart", handleDocumentDragStart);
    document.addEventListener("dragend", handleDocumentDragEnd);

    // Drag state is also reset from capture-phase window listeners: a child
    // handler that calls stopPropagation() (or throws) can no longer keep the
    // overlay on. Capture also runs before the container's own drop handler,
    // so the overlay is already gone while the upload is being set up.
    /** @param {DragEvent} event */
    const handleWindowDragOverCapture = (event) => {
      if (hasFiles(event)) event.preventDefault();
    };
    /** @param {DragEvent} event */
    const handleWindowDropCapture = (event) => {
      if (hasFiles(event)) event.preventDefault();
      endDrag();
    };
    const handleWindowDragEnd = () => endDrag();
    const handleWindowBlur = () => resetDragState();
    /** @param {KeyboardEvent} event */
    const handleWindowKeyDown = (event) => {
      // Esc cancels a native drag; Firefox may not send dragleave for it.
      if (event.key === "Escape" && (isDragging || isInternalDrag)) endDrag();
    };
    /** @param {PointerEvent} event */
    const handleWindowPointer = (event) => {
      // Only the external-file overlay needs this fallback. A tree drag ends
      // through its own pointerup/cancel handlers, so a stray pointer event
      // must not clear it.
      if (!isDragging) return;
      // A pointerdown means the previous drag session is definitely over.
      // While a native drag is running the browser suppresses mouse/pointer
      // events, so one arriving with no button held is also terminal.
      if (event.type === "pointerdown" || event.buttons === 0) endDrag();
    };
    const handleVisibilityChange = () => {
      if (document.hidden) resetDragState();
    };

    window.addEventListener("dragover", handleWindowDragOverCapture, true);
    window.addEventListener("drop", handleWindowDropCapture, true);
    window.addEventListener("dragend", handleWindowDragEnd, true);
    // Non-passive: while an internal drag is active this takes over the wheel
    // so the tree scrolls even if Firefox targets the event outside the panel.
    window.addEventListener("wheel", handleTreeWheel, {
      capture: true,
      passive: false,
    });
    window.addEventListener("blur", handleWindowBlur);
    window.addEventListener("keydown", handleWindowKeyDown, true);
    window.addEventListener("pointerdown", handleWindowPointer, true);
    window.addEventListener("pointerup", handleWindowPointer, true);
    window.addEventListener("pointermove", handleWindowPointer, true);
    // Internal moves are pointer-driven; these listeners follow the press,
    // the threshold, the hovered drop target and the release.
    window.addEventListener("pointermove", handleTreePointerMove, true);
    window.addEventListener("pointerup", handleTreePointerUp, true);
    window.addEventListener("pointercancel", handleTreePointerCancel, true);
    /** @param {MouseEvent} event */
    const handleDragClick = (event) => {
      if (!suppressTreeClick) return;
      suppressTreeClick = false;
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("click", handleDragClick, true);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      resetDragState();
      window.fetch = originalFetch; // Restore original fetch
      window.removeEventListener("refreshFileTree", loadFileTree);
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("dragstart", handleDocumentDragStart);
      document.removeEventListener("dragend", handleDocumentDragEnd);
      window.removeEventListener("dragover", handleWindowDragOverCapture, true);
      window.removeEventListener("drop", handleWindowDropCapture, true);
      window.removeEventListener("dragend", handleWindowDragEnd, true);
      window.removeEventListener("wheel", handleTreeWheel, true);
      window.removeEventListener("blur", handleWindowBlur);
      window.removeEventListener("keydown", handleWindowKeyDown, true);
      window.removeEventListener("pointerdown", handleWindowPointer, true);
      window.removeEventListener("pointerup", handleWindowPointer, true);
      window.removeEventListener("pointermove", handleWindowPointer, true);
      window.removeEventListener("pointermove", handleTreePointerMove, true);
      window.removeEventListener("pointerup", handleTreePointerUp, true);
      window.removeEventListener(
        "pointercancel",
        handleTreePointerCancel,
        true,
      );
      window.removeEventListener("click", handleDragClick, true);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      resetDragState();
    };
  });

  $effect(() => {
    if (!$isAuthenticated) {
      // Reset so the next login loads a fresh tree.
      treeRequested = false;
      return;
    }
    if (treeRequested) return;
    treeRequested = true;
    loadFileTree();
  });

  // Event handler for opening logs
  function handleOpenLogs() {
    showLogViewer = true;
  }

  $effect(() => {
    // Setup event listener
    window.addEventListener("openLogs", handleOpenLogs);

    return () => {
      window.removeEventListener("openLogs", handleOpenLogs);
    };
  });

  $effect(() => {
    if (!$settings.enablePlayer && audioFile) {
      // Player was disabled - clean up audio
      if (audioFile?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(audioFile.url);
      }
      audioFile = null;

      // If you want to also stop any playing audio through the player component
      if (playerComponent?.stop) {
        playerComponent.stop();
      }
    }
  });

  $effect(() => {
    // When selected file changes OR player enabled setting changes
    if ($settings.enablePlayer && selectedFile) {
      // Check if it's an audio file
      const isAudio = selectedFile.match(
        /\.(mp3|flac|wav|aif|aiff|aac|ogg|m4a|wma|opus|ape|dsf|dff)$/i,
      );

      if (isAudio) {
        // Only load if it's a different file or audioFile is null
        if (!audioFile || audioFile.originalName !== selectedFile) {
          loadAudioFile(selectedFile);
        }
      } else if (audioFile) {
        // Selected file is not audio but we have an audio file loaded - clear it
        if (audioFile?.url?.startsWith("blob:")) {
          URL.revokeObjectURL(audioFile.url);
        }
        audioFile = null;
      }
    } else if (!$settings.enablePlayer && audioFile) {
      // Player was disabled - clean up audio
      if (audioFile?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(audioFile.url);
      }
      audioFile = null;
    }
  });
</script>

{#if !$isAuthenticated}
  <Login />
{:else}
  <div
    role="region"
    class="container"
    bind:this={appContainer}
    ondragenter={handleDragEnter}
    ondragover={handleDragOver}
    ondragleave={handleDragLeave}
    ondrop={handleDrop}
    onpointerdown={handleTreePointerDown}
    class:dragging={isDragging}
  >
    <!-- Theme switch, help toggle and settings toggle -->
    <div class="theme-toggle-group">
      <button
        class="settings-toggle"
        class:blurred={isDragging}
        onclick={() => (showSettingsModal = true)}
        title="Settings"
      >
        <span>Settings</span>
      </button>
      <button
        class="help-toggle"
        class:blurred={isDragging}
        onclick={() => (showHelpModal = true)}
        title="Help & Information"
      >
        <span>Help</span>
      </button>
      <button
        class="theme-toggle"
        class:blurred={isDragging}
        onclick={toggleTheme}
      >
        {#if $theme === "light"}
          <span>Light</span>
        {:else}
          <span>Dark</span>
        {/if}
      </button>
    </div>

    <!-- Byte progress bar for uploads -->
    {#if showProgressBar}
      <div
        class="upload-progress-bar"
        class:indeterminate={$upload.phase === "preparing" ||
          $upload.phase === "refreshing" ||
          $upload.totalBytes === 0}
        style="width: {uploadPercent}%;"
      ></div>
    {/if}

    <!-- Toast notifications -->
    <ToastContainer />
    <UploadTray />

    <!-- Main split layout -->
    <div class="split-container" class:blurred={isDragging}>
      <!-- Left Panel - Folder Navigation / File Selection -->
      <div class="panel left-panel" style="width: {leftPanelWidth}%;">
        <div class="panel-header">
          <h3>File Browser</h3>
          <div class="header-actions">
            <!-- User info and logout -->
            <button class="logout-btn" onclick={handleLogout} title="Logout">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              Logout
            </button>
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

            <!-- Create folder in root button -->
            <button
              class="create-folder-btn"
              onclick={() => handleCreateFolder("")}
              title="Create folder in root"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"
                />
                <line x1="12" y1="11" x2="12" y2="17" />
                <line x1="9" y1="14" x2="15" y2="14" />
              </svg>
              <span>New Folder</span>
            </button>

            <!-- Upload folder button -->
            <button
              class="create-folder-btn"
              onclick={() => folderInput?.click()}
              title="Upload a folder from this computer"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span>Upload</span>
            </button>
            <input
              bind:this={folderInput}
              type="file"
              webkitdirectory
              multiple
              class="hidden-file-input"
              onchange={handleFolderInput}
            />

            <!-- Search input -->
            <div class="search-container">
              <input
                type="text"
                class="search-input"
                placeholder="Search files..."
                bind:value={searchQuery}
                onkeydown={(e) => {
                  if (e.key === "Escape") {
                    searchQuery = "";
                  }
                }}
              />
              {#if searchQuery}
                <button
                  class="search-clear"
                  onclick={() => (searchQuery = "")}
                  title="Clear search"
                >
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
              {/if}
            </div>
            <SortButton />
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

        <div
          class="panel-content file-tree-panel"
          bind:this={fileTreeContainer}
        >
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
                  {#each sortedTreeData as item (item.path)}
                    <TreeNode
                      {item}
                      expanded={expandedDirs}
                      {toggleDir}
                      {selectFile}
                      {selectFolder}
                      {selectedFolder}
                      {selectedFile}
                      onRename={handleRename}
                      onDelete={handleDelete}
                      onCreateFolder={handleCreateFolder}
                      onCopy={handleCopyItem}
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
          <h3>
            {#if selectedFile && selectedFile.match(/\.(jpg|jpeg|png|gif|bmp|webp)$/i)}
              Image Viewer
            {:else if selectedFile && selectedFile.match(/\.(txt|lrc)$/i)}
              Text Editor
            {:else if selectedFile && !isAudioFile(selectedFile)}
              File Info (read-only)
            {:else if selectedFile}
              Metadata Editor
            {:else if selectedFolder && !selectedFile}
              Folder Overview
            {:else}
              File Viewer
            {/if}
          </h3>
          {#if selectedFolder && !selectedFile}
            <button
              class="toggle-overview-btn"
              class:active={showFolderOverview}
              onclick={() => (showFolderOverview = !showFolderOverview)}
              title="Toggle folder metadata overview"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
            </button>
          {/if}
        </div>

        <div class="panel-content">
          {#if selectedFile && selectedFile.match(/\.(jpg|jpeg|png|gif|bmp|webp)$/i)}
            <ImageViewer filePath={selectedFile} />
          {:else if selectedFile && selectedFile.match(/\.(txt|lrc)$/i)}
            <TextEditor filePath={selectedFile} />
          {:else if selectedFile}
            <MetadataEditor filePath={selectedFile} />
          {:else if selectedFolder && showFolderOverview}
            <FolderOverview
              folderPath={selectedFolder}
              audioFiles={audioFilesInFolder}
            />
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
              <p>Select a file to view or edit</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>

  <!-- Player component -->
  <div class="player-wrapper" class:blurred={isDragging}>
    <Player {audioFile} bind:this={playerComponent} />
  </div>
  <HelpModal
    isOpen={showHelpModal}
    onClose={() => (showHelpModal = false)}
    {currentVersion}
    {gitSha}
  />
  <LogViewer isOpen={showLogViewer} onClose={() => (showLogViewer = false)} />
  <SettingsModal
    isOpen={showSettingsModal}
    onClose={() => (showSettingsModal = false)}
  />
{/if}
