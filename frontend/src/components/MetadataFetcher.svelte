<!-- src/components/MetadataFetcher.svelte -->
<script>
  import {
    toast,
    getFieldLabel,
    getFieldDescription,
    isAudioFile,
  } from "../utils/index.js";
  import CoverPreview from "./CoverPreview.svelte";

  let { isOpen, onClose, mode, targetPath, isFolder = false } = $props();

  // ---------- State ----------
  let addons = $state([]);
  let selectedAddonId = $state("");
  let query = $state("");
  let limit = $state(5);
  let isSearching = $state(false);
  let searchResults = $state([]);
  let selectedResultId = $state(null);

  let fetchedTracks = $state([]);
  let selectedTrackIndex = $state(0);
  let singleFileFields = $state(new Set());

  let folderFiles = $state([]);
  let fileAssignments = $state([]);
  let fileEnabled = $state([]);
  let fileFieldSets = $state([]);

  let fetchedSong = $state(null);
  let songFields = $state(new Set());

  let isFetching = $state(false);
  let isApplying = $state(false);
  let queryInput = $state(null);

  let allFields = $state(new Set()); // all available fields
  let globalSelectedFields = $state(new Set()); // which fields are selected globally

  let globalFieldsExpanded = $state(true);

  // Presets for global field selection
  const PRESETS = [
    { label: "All", fields: [] },
    { label: "None", fields: [] },
    {
      label: "Main fields",
      fields: [
        "title",
        "album",
        "artist",
        "albumArtist",
        "trackNumber",
        "diskNumber",
        "date",
        "genre",
        "picture",
      ],
    },
    { label: "Coverart only", fields: ["picture"] },
    { label: "Lyrics only", fields: ["lyrics", "unsyncedLyrics"] },
  ];

  const placeholderImage =
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' fill='%23e0e0e0'/%3E%3Ccircle cx='20' cy='20' r='12' fill='none' stroke='%23aaaaaa' stroke-width='2'/%3E%3Ccircle cx='20' cy='20' r='4' fill='%23aaaaaa'/%3E%3Ccircle cx='20' cy='20' r='1.5' fill='%23e0e0e0'/%3E%3C/svg%3E";

  const LAST_ADDON_KEY = "md_lastAddonId";

  // Display-only field addons may return in search results and fetched
  // metadata. It is shown in the UI but never offered or written as a tag.
  const EXTRA_INFO_FIELD = "extraInfo";

  // ---------- Helper functions ----------
  function isExtraInfoKey(key) {
    return key === EXTRA_INFO_FIELD || key === "extra_info";
  }

  function getExtraInfo(metadata) {
    if (!metadata) return "";
    const value = metadata[EXTRA_INFO_FIELD] ?? metadata.extra_info;
    if (value === undefined || value === null) return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value).trim();
  }

  function selectableFields(metadata) {
    return Object.keys(metadata || {}).filter((key) => !isExtraInfoKey(key));
  }

  function metadataEntries(metadata) {
    return Object.entries(metadata || {}).filter(
      ([key]) => !isExtraInfoKey(key),
    );
  }

  async function getAudioFilesInFolder(folderPath) {
    try {
      const res = await fetch("/api/files");
      if (!res.ok) throw new Error("Failed to fetch file tree");
      const tree = await res.json();

      function findFolder(node, path) {
        if (node.path === path && node.type === "directory") return node;
        if (node.children) {
          for (const child of node.children) {
            const found = findFolder(child, path);
            if (found) return found;
          }
        }
        return null;
      }

      const folderNode = findFolder({ path: "", children: tree }, folderPath);
      if (!folderNode) return [];
      const audioFiles = folderNode.children.filter(
        (f) => f.type === "file" && isAudioFile(f.name, f.file_type),
      );
      return audioFiles.map((f) => ({ path: f.path, name: f.name }));
    } catch (e) {
      toast.error("Failed to list folder files: " + e.message);
      return [];
    }
  }

  async function loadAddons() {
    try {
      const res = await fetch("/api/addons");
      if (!res.ok) throw new Error("Failed to load addons");
      const data = await res.json();
      const all = data.fetchers || [];
      const method = mode === "song" ? "search_songs" : "search_albums";
      addons = all.filter((a) => a.methods && a.methods.includes(method));

      if (addons.length > 0) {
        const storedId = localStorage.getItem(LAST_ADDON_KEY);
        if (storedId && addons.some((a) => a.id === storedId)) {
          selectedAddonId = storedId;
        } else {
          selectedAddonId = addons[0].id;
        }
      } else {
        selectedAddonId = "";
        toast.warning(`No addon supports ${method}`);
      }
    } catch (e) {
      toast.error(`Failed to load addons: ${e.message}`);
    }
  }

  $effect(() => {
    if (selectedAddonId) {
      localStorage.setItem(LAST_ADDON_KEY, selectedAddonId);
    }
  });

  async function prefillQuery() {
    let filePath = targetPath;
    if (isFolder) {
      const files = await getAudioFilesInFolder(targetPath);
      folderFiles = files;
      if (files.length === 0) {
        toast.warning("No audio files found in folder");
        return;
      }
      filePath = files[0].path;
    }
    if (!filePath) return;
    try {
      const res = await fetch(
        `/api/metadata?path=${encodeURIComponent(filePath)}`,
      );
      if (!res.ok) throw new Error("Failed to fetch metadata");
      const data = await res.json();
      if (mode === "song") {
        query = data.title || data.filename || filePath.split("/").pop();
      } else {
        query = data.album || data.filename || filePath.split("/").pop();
      }
    } catch (e) {
      query = filePath.split("/").pop();
    }
  }

  $effect(() => {
    if (isOpen) {
      loadAddons();
      prefillQuery();
      searchResults = [];
      selectedResultId = null;
      fetchedTracks = [];
      fetchedSong = null;
      folderFiles = [];
      fileAssignments = [];
      fileEnabled = [];
      fileFieldSets = [];
      singleFileFields = new Set();
      songFields = new Set();
      selectedTrackIndex = 0;
      isFetching = false;
    }
  });

  $effect(() => {
    if (isOpen && queryInput) {
      queryInput.focus();
      queryInput.select();
    }
  });

  async function handleSearch() {
    if (!selectedAddonId || !query.trim()) {
      toast.warning("Please select an add‑on and enter a query");
      return;
    }
    isSearching = true;
    searchResults = [];
    selectedResultId = null;
    fetchedTracks = [];
    fetchedSong = null;
    try {
      const endpoint = mode === "song" ? "search_songs" : "search_albums";
      const url = `/api/addons/${selectedAddonId}/${endpoint}?query=${encodeURIComponent(query)}&limit=${limit}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      if (data.success) {
        searchResults = data.results || [];
        if (searchResults.length === 0) toast.info("No results found");
      } else {
        toast.error(data.error || "Search error");
      }
    } catch (e) {
      toast.error(`Search error: ${e.message}`);
    } finally {
      isSearching = false;
    }
  }

  async function selectResult(resultId) {
    selectedResultId = resultId;
    isFetching = true;
    fetchedTracks = [];
    fetchedSong = null;
    try {
      let url;
      if (mode === "song") {
        url = `/api/addons/${selectedAddonId}/fetch_song/${resultId}`;
      } else {
        url = `/api/addons/${selectedAddonId}/fetch_album/${resultId}`;
      }
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch metadata");
      const data = await res.json();
      if (data.success) {
        if (mode === "song") {
          fetchedSong = data.metadata;
          songFields = new Set(selectableFields(fetchedSong));
        } else {
          const tracks = data.metadata || [];
          fetchedTracks = tracks;
          if (tracks.length === 0) {
            toast.warning("No tracks found in album");
            isFetching = false;
            return;
          }
          if (isFolder) {
            if (folderFiles.length === 0) {
              toast.warning("No audio files in folder");
              isFetching = false;
              return;
            }
            autoMatchFilesToTracks(tracks);

            // Compute union of all field keys from all tracks
            const allKeys = new Set();
            tracks.forEach((t) =>
              selectableFields(t).forEach((k) => allKeys.add(k)),
            );
            allFields = allKeys;
            globalSelectedFields = new Set(allKeys); // start with all selected

            // Initialize each file's field set to the global selection
            fileFieldSets = folderFiles.map(
              () => new Set(globalSelectedFields),
            );
            fileEnabled = folderFiles.map(() => true);

            fileEnabled = folderFiles.map(() => true);
            fileFieldSets = folderFiles.map((file, idx) => {
              const assign = fileAssignments.find((a) => a.fileIndex === idx);
              if (assign && assign.trackIndex !== null) {
                const track = fetchedTracks[assign.trackIndex];
                if (track) return new Set(selectableFields(track));
              }
              return new Set();
            });
          } else {
            selectedTrackIndex = 0;
            singleFileFields = new Set(selectableFields(tracks[0]));
          }
        }
      } else {
        toast.error(data.error || "Failed to fetch metadata");
      }
    } catch (e) {
      toast.error(`Fetch error: ${e.message}`);
    } finally {
      isFetching = false;
    }
  }

  function getTrackNumber(track) {
    return track.trackNumber ?? track.track;
  }

  function autoMatchFilesToTracks(tracks) {
    if (!folderFiles.length || !tracks.length) {
      fileAssignments = [];
      return;
    }
    const sortedFiles = [...folderFiles].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true }),
    );
    const sortedTracks = [...tracks].sort((a, b) => {
      const aTrack = getTrackNumber(a)
        ? parseInt(getTrackNumber(a))
        : Infinity;
      const bTrack = getTrackNumber(b)
        ? parseInt(getTrackNumber(b))
        : Infinity;
      return aTrack - bTrack;
    });
    const mapping = folderFiles.map((file, idx) => ({
      fileIndex: idx,
      trackIndex: idx < sortedTracks.length ? idx : null,
    }));
    fileAssignments = mapping;
  }

  function toggleFileEnabled(index) {
    fileEnabled[index] = !fileEnabled[index];
    fileEnabled = [...fileEnabled];
  }

  function updateFileTrack(fileIndex, trackIndex) {
    const newAssign = fileAssignments.map((a) =>
      a.fileIndex === fileIndex
        ? { ...a, trackIndex: trackIndex === "" ? null : Number(trackIndex) }
        : a,
    );
    fileAssignments = newAssign;
    const assign = fileAssignments.find((a) => a.fileIndex === fileIndex);
    if (assign && assign.trackIndex !== null) {
      const track = fetchedTracks[assign.trackIndex];
      if (track) {
        fileFieldSets[fileIndex] = new Set(globalSelectedFields);
      } else {
        fileFieldSets[fileIndex] = new Set();
      }
    } else {
      fileFieldSets[fileIndex] = new Set();
    }
    fileFieldSets = [...fileFieldSets];
  }

  function toggleFileField(fileIndex, field) {
    const set = fileFieldSets[fileIndex];
    if (set.has(field)) set.delete(field);
    else set.add(field);
    fileFieldSets = [...fileFieldSets];
  }

  function toggleSingleField(field) {
    if (mode === "song") {
      if (songFields.has(field)) songFields.delete(field);
      else songFields.add(field);
      songFields = new Set(songFields);
    } else {
      if (singleFileFields.has(field)) singleFileFields.delete(field);
      else singleFileFields.add(field);
      singleFileFields = new Set(singleFileFields);
    }
  }

  async function applyMetadata() {
    isApplying = true;
    try {
      if (isFolder && mode === "album") {
        let updatedCount = 0;
        for (let i = 0; i < folderFiles.length; i++) {
          if (!fileEnabled[i]) continue;
          const assign = fileAssignments.find((a) => a.fileIndex === i);
          if (!assign || assign.trackIndex === null) continue;
          const track = fetchedTracks[assign.trackIndex];
          if (!track) continue;
          const fields = Array.from(fileFieldSets[i] || new Set());
          if (fields.length === 0) continue;
          const file = folderFiles[i];
          for (const field of fields) {
            if (isExtraInfoKey(field)) continue;
            if (field === "picture") {
              if (track.picture) {
                await uploadCoverArt(file.path, track.picture);
              }
              continue;
            }
            let value = track[field];
            if (value !== undefined && value !== null) {
              await updateSingleFile(file.path, field, String(value));
            }
          }
          updatedCount++;
        }
        toast.success(`Metadata applied to ${updatedCount} file(s)`);
      } else if (!isFolder && mode === "album") {
        const track = fetchedTracks[selectedTrackIndex];
        if (!track) {
          toast.warning("No track selected");
          return;
        }
        const fields = Array.from(singleFileFields);
        for (const field of fields) {
          if (isExtraInfoKey(field)) continue;
          if (field === "picture") {
            if (track.picture) await uploadCoverArt(targetPath, track.picture);
            continue;
          }
          let value = track[field];
          if (value !== undefined && value !== null) {
            await updateSingleFile(targetPath, field, String(value));
          }
        }
        toast.success("Metadata applied to file");
      } else if (mode === "song") {
        if (!fetchedSong) {
          toast.warning("No metadata to apply");
          return;
        }
        const fields = Array.from(songFields);
        for (const field of fields) {
          if (isExtraInfoKey(field)) continue;
          if (field === "picture") {
            if (fetchedSong.picture)
              await uploadCoverArt(targetPath, fetchedSong.picture);
            continue;
          }
          let value = fetchedSong[field];
          if (value !== undefined && value !== null) {
            await updateSingleFile(targetPath, field, String(value));
          }
        }
        toast.success("Metadata applied to file");
      }
      window.dispatchEvent(new CustomEvent("refreshFileTree"));
      window.dispatchEvent(
        new CustomEvent("refreshMetadata", { detail: { path: targetPath } }),
      );
      onClose();
    } catch (e) {
      toast.error(`Apply failed: ${e.message}`);
    } finally {
      isApplying = false;
    }
  }

  async function updateSingleFile(filePath, field, value) {
    const res = await fetch("/api/metadata/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: filePath, field, value }),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to update ${field}: ${error}`);
    }
  }

  async function uploadCoverArt(filePath, pictureData) {
    // 1. If it's a Base64 data URL, convert and upload as file
    if (pictureData.startsWith("data:")) {
      const response = await fetch(pictureData);
      const blob = await response.blob();
      const file = new File([blob], "cover.jpg", {
        type: blob.type || "image/jpeg",
      });
      const formData = new FormData();
      formData.append("file", file);
      formData.append("path", filePath);

      const uploadRes = await fetch("/api/metadata/picture/file", {
        method: "POST",
        body: formData,
      });
      if (!uploadRes.ok) throw new Error("Failed to update cover art");
      return;
    }

    // 2. If it's a remote URL, bypass browser fetch and let server handle download
    if (isImageUrl(pictureData)) {
      const uploadRes = await fetch("/api/metadata/picture/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: filePath, url: pictureData }),
      });
      if (!uploadRes.ok) throw new Error("Failed to update cover art from URL");
      return;
    }

    toast.error("Unsupported image format");
  }

  function displayValue(value) {
    if (
      typeof value === "string" &&
      (value.startsWith("data:image") || isImageUrl(value))
    )
      return "[Image]";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function isPictureField(key, value) {
    return (
      key === "picture" &&
      value &&
      typeof value === "string" &&
      (value.startsWith("data:image") || isImageUrl(value))
    );
  }

  function isImageUrl(value) {
    return (
      typeof value === "string" &&
      (value.startsWith("http://") || value.startsWith("https://"))
    );
  }

  function toggleGlobalField(field) {
    if (globalSelectedFields.has(field)) {
      globalSelectedFields.delete(field);
    } else {
      globalSelectedFields.add(field);
    }
    globalSelectedFields = new Set(globalSelectedFields);
    // Apply to all files
    for (let i = 0; i < fileFieldSets.length; i++) {
      fileFieldSets[i] = new Set(globalSelectedFields);
    }
    fileFieldSets = [...fileFieldSets];
  }

  function toggleGlobalFields() {
    globalFieldsExpanded = !globalFieldsExpanded;
  }

  function applyPreset(preset) {
    let fields;
    if (preset.label === "All") {
      fields = new Set(allFields);
    } else if (preset.label === "None") {
      fields = new Set();
    } else {
      // Only include fields that actually exist in the fetched tracks
      fields = new Set(preset.fields.filter((f) => allFields.has(f)));
    }
    globalSelectedFields = fields;
    // Apply to all file cards
    for (let i = 0; i < fileFieldSets.length; i++) {
      fileFieldSets[i] = new Set(globalSelectedFields);
    }
    fileFieldSets = [...fileFieldSets];
  }

  function applySongPreset(preset) {
    if (!fetchedSong) return;
    let fields;
    if (preset.label === "All") {
      fields = new Set(selectableFields(fetchedSong));
    } else if (preset.label === "None") {
      fields = new Set();
    } else {
      // Only include fields that exist on the fetched song
      fields = new Set(
        preset.fields.filter((f) => fetchedSong.hasOwnProperty(f)),
      );
    }
    songFields = fields;
  }

  function applySingleTrackPreset(preset) {
    const track = fetchedTracks[selectedTrackIndex];
    if (!track) return;
    let fields;
    if (preset.label === "All") {
      fields = new Set(selectableFields(track));
    } else if (preset.label === "None") {
      fields = new Set();
    } else {
      fields = new Set(preset.fields.filter((f) => track.hasOwnProperty(f)));
    }
    singleFileFields = fields;
  }
</script>

{#if isOpen}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="modal-overlay" onclick={onClose}>
    <div class="modal-container" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>
          {#if mode === "song"}Fetch Song Metadata
          {:else if isFolder}Fetch Album Metadata (Folder Batch)
          {:else}Fetch Album Metadata (Single File)
          {/if}
        </h2>
        <button class="close-btn" onclick={onClose}>✕</button>
      </div>

      <div class="modal-body">
        <!-- Addon, query, limit -->
        <div class="form-group">
          <!-- svelte-ignore a11y_label_has_associated_control -->
          <label>Add‑on</label>
          <select bind:value={selectedAddonId}>
            {#each addons as addon}
              <option value={addon.id}>{addon.name}</option>
            {/each}
          </select>
        </div>
        <div class="form-row">
          <div class="form-group">
            <!-- svelte-ignore a11y_label_has_associated_control -->
            <label>Query</label>
            <input
              bind:this={queryInput}
              type="text"
              bind:value={query}
              placeholder="Search..."
              onkeydown={(e) => {
                if (e.key === "Enter") handleSearch();
              }}
            />
          </div>
          <div class="form-group">
            <!-- svelte-ignore a11y_label_has_associated_control -->
            <label>Limit</label>
            <input type="number" bind:value={limit} min="1" max="50" />
          </div>
        </div>
        <button
          class="search-btn"
          onclick={handleSearch}
          disabled={isSearching || !selectedAddonId}
        >
          {isSearching ? "Searching..." : "Search"}
        </button>

        <!-- Search results -->
        {#if isSearching}
          <div class="loading">Searching…</div>
        {:else if searchResults.length > 0}
          <div class="results-list">
            {#each searchResults as result}
              <div
                class="result-item"
                class:selected={selectedResultId === result.id}
                onclick={() => selectResult(result.id)}
              >
                <div class="result-info">
                  {#if mode === "song"}
                    <strong>{result.title}</strong> - {result.artist}
                  {:else}
                    <strong>{result.title}</strong> - {result.artist}
                    {result.date || result.year
                      ? `(${result.date || result.year})`
                      : ""}
                  {/if}
                  {#if getExtraInfo(result)}
                    <div class="result-extra-info">{getExtraInfo(result)}</div>
                  {/if}
                </div>
                <CoverPreview
                  url={result.coverart}
                  alt="cover"
                  variant="result"
                  placeholder={placeholderImage}
                  showSourceLink={false}
                />
              </div>
            {/each}
          </div>
        {/if}

        <!-- Fetched metadata -->
        {#if isFetching}
          <div class="loading">Fetching metadata…</div>
        {:else if mode === "song" && fetchedSong}
          <div class="metadata-preview">
            <h3>Song Metadata</h3>
            {#if getExtraInfo(fetchedSong)}
              <div class="extra-info">{getExtraInfo(fetchedSong)}</div>
            {/if}
            <div class="presets">
              {#each PRESETS as preset}
                <button
                  class="preset-btn"
                  onclick={() => applySongPreset(preset)}
                >
                  {preset.label}
                </button>
              {/each}
            </div>
            <div class="fields-list">
              {#each metadataEntries(fetchedSong) as [key, value]}
                <div class="field-item">
                  <label title={getFieldDescription(key) || undefined}>
                    <input
                      type="checkbox"
                      checked={songFields.has(key)}
                      onchange={() => toggleSingleField(key)}
                    />
                    {getFieldLabel(key)}:
                  </label>
                  {#if isPictureField(key, value)}
                    <CoverPreview url={value} alt="cover" />
                  {:else}
                    <span class="field-value">{displayValue(value)}</span>
                  {/if}
                </div>
              {/each}
            </div>
          </div>
        {:else if mode === "album" && fetchedTracks.length > 0}
          {#if isFolder}
            <!-- Batch mode -->
            <div class="batch-container">
              <!-- Global field selection -->
              <div class="global-fields">
                <div class="global-header" onclick={toggleGlobalFields}>
                  <h4>Global filter</h4>
                  <span class="toggle-icon"
                    >{globalFieldsExpanded ? "▼" : "▶"}</span
                  >
                </div>
                {#if globalFieldsExpanded}
                  <div class="presets">
                    {#each PRESETS as preset}
                      <button
                        class="preset-btn"
                        onclick={() => applyPreset(preset)}
                      >
                        {preset.label}
                      </button>
                    {/each}
                  </div>
                  <div class="fields-list">
                    {#each Array.from(allFields) as field}
                      <div class="field-item">
                        <label title={getFieldDescription(field) || undefined}>
                          <input
                            type="checkbox"
                            checked={globalSelectedFields.has(field)}
                            onchange={() => toggleGlobalField(field)}
                          />
                          {getFieldLabel(field)}:
                        </label>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
              <!-- File cards -->
              <h3>Files in folder</h3>
              <div class="file-cards">
                {#each folderFiles as file, fileIndex}
                  {@const assign = fileAssignments.find(
                    (a) => a.fileIndex === fileIndex,
                  )}
                  {@const trackIndex = assign ? assign.trackIndex : null}
                  {@const track =
                    trackIndex !== null ? fetchedTracks[trackIndex] : null}
                  {@const enabled = fileEnabled[fileIndex] || false}
                  {@const fields = fileFieldSets[fileIndex] || new Set()}

                  <div class="file-card" class:disabled={!enabled}>
                    <div class="file-header">
                      <label class="file-enable">
                        <input
                          type="checkbox"
                          checked={enabled}
                          onchange={() => toggleFileEnabled(fileIndex)}
                        />
                        <span class="file-name">{file.name}</span>
                      </label>
                      <select
                        value={trackIndex ?? ""}
                        onchange={(e) =>
                          updateFileTrack(fileIndex, e.target.value)}
                        disabled={!enabled}
                      >
                        <option value="">Skip</option>
                        {#each fetchedTracks as t, idx}
                          <option value={idx}>
                            {getTrackNumber(t)
                              ? `Track ${getTrackNumber(t)}: `
                              : ""}{t.title ||
                              "Untitled"}
                          </option>
                        {/each}
                      </select>
                    </div>

                    {#if track && getExtraInfo(track)}
                      <div class="extra-info">{getExtraInfo(track)}</div>
                    {/if}

                    {#if enabled && track}
                      <div class="file-fields">
                        {#each metadataEntries(track) as [key, value]}
                          <div class="field-item">
                            <label title={getFieldDescription(key) || undefined}>
                              <input
                                type="checkbox"
                                checked={fields.has(key)}
                                onchange={() => toggleFileField(fileIndex, key)}
                              />
                              {getFieldLabel(key)}:
                            </label>
                            {#if isPictureField(key, value)}
                              <CoverPreview url={value} alt="cover" />
                            {:else}
                              <span class="field-value"
                                >{displayValue(value)}</span
                              >
                            {/if}
                          </div>
                        {/each}
                      </div>
                    {:else if enabled && !track}
                      <div class="no-track-message">No track assigned</div>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {:else}
            <!-- Single file album -->
            <div class="track-selector">
              <!-- svelte-ignore a11y_label_has_associated_control -->
              <label>Select track to apply:</label>
              <select bind:value={selectedTrackIndex}>
                {#each fetchedTracks as track, idx}
                  <option value={idx}>
                    {getTrackNumber(track)
                      ? `Track ${getTrackNumber(track)}: `
                      : ""}{track.title ||
                      "Untitled"}
                  </option>
                {/each}
              </select>
            </div>
            <div class="metadata-preview">
              <h3>Track Metadata</h3>
              {#if getExtraInfo(fetchedTracks[selectedTrackIndex])}
                <div class="extra-info">
                  {getExtraInfo(fetchedTracks[selectedTrackIndex])}
                </div>
              {/if}
              <div class="presets">
                {#each PRESETS as preset}
                  <button
                    class="preset-btn"
                    onclick={() => applySingleTrackPreset(preset)}
                  >
                    {preset.label}
                  </button>
                {/each}
              </div>
              <div class="fields-list">
                {#each metadataEntries(fetchedTracks[selectedTrackIndex]) as [key, value]}
                  <div class="field-item">
                    <label title={getFieldDescription(key) || undefined}>
                      <input
                        type="checkbox"
                        checked={singleFileFields.has(key)}
                        onchange={() => toggleSingleField(key)}
                      />
                      {getFieldLabel(key)}:
                    </label>
                    {#if isPictureField(key, value)}
                      <CoverPreview url={value} alt="cover" />
                    {:else}
                      <span class="field-value">{displayValue(value)}</span>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        {/if}
      </div>

      <div class="modal-footer">
        <button class="cancel-btn" onclick={onClose}>Cancel</button>
        <button
          class="apply-btn"
          onclick={applyMetadata}
          disabled={isApplying || (!fetchedSong && fetchedTracks.length === 0)}
        >
          {isApplying ? "Applying…" : "Apply Selected"}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.2s ease;
  }

  .modal-container {
    background: white;
    border-radius: 8px;
    width: 90%;
    max-width: 900px;
    max-height: calc(90vh - 80px);
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    animation: scaleIn 0.2s ease;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #333;
  }

  .close-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #888;
    padding: 0 8px;
  }
  .close-btn:hover {
    color: #333;
  }

  .modal-body {
    padding: 20px;
    overflow-y: auto;
    flex: 1;
  }

  .form-group {
    margin-bottom: 12px;
  }
  .form-group label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: #555;
    margin-bottom: 4px;
  }
  .form-group select,
  .form-group input {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
    box-sizing: border-box;
    background: white;
  }
  .form-row {
    display: flex;
    gap: 12px;
  }
  .form-row .form-group {
    flex: 1;
  }

  .search-btn {
    background: var(--color-primary);
    color: white;
    border: none;
    padding: 8px 20px;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
    margin-top: 4px;
  }
  .search-btn:hover {
    background: var(--color-primary-focus);
  }
  .search-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .loading {
    text-align: center;
    padding: 20px;
    color: #888;
  }

  .results-list {
    margin-top: 16px;
    border: 1px solid #eee;
    border-radius: 4px;
  }

  .result-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid #f5f5f5;
    cursor: pointer;
  }
  .result-item:last-child {
    border-bottom: none;
  }
  .result-item:hover {
    background: #f9f9f9;
  }
  .result-item.selected {
    background: var(--color-primary-transparent);
    border-left: 3px solid var(--color-primary);
    border-radius: 3px;
  }
  .result-extra-info {
    margin-top: 2px;
    font-size: 12px;
    color: #777;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .metadata-preview {
    margin-top: 20px;
    border-top: 1px solid #eee;
    padding-top: 16px;
  }
  .metadata-preview h3 {
    font-size: 16px;
    font-weight: 600;
    color: #333;
    margin: 0 0 12px 0;
  }

  .extra-info {
    margin-bottom: 12px;
    padding: 8px 10px;
    border-left: 3px solid var(--color-primary);
    border-radius: 4px;
    background: var(--color-primary-transparent);
    color: #555;
    font-size: 13px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .fields-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    font-size: 14px;
    align-items: flex-start;
  }
  .field-item label {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    min-width: 400px;
    flex-shrink: 0;
  }
  .field-item input[type="checkbox"] {
    margin: 0;
    accent-color: var(--color-primary);
  }
  .field-value {
    color: #555;
    word-break: break-word;
    white-space: pre-wrap;
  }

  .batch-container {
    margin-top: 20px;
    border-top: 1px solid #eee;
    padding-top: 16px;
  }
  .batch-container h3 {
    font-size: 16px;
    font-weight: 600;
    color: #333;
    margin: 0 0 12px 0;
  }

  .file-cards {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .file-card {
    border: 1px solid #eee;
    border-radius: 6px;
    padding: 12px;
    background: #fafafa;
  }
  .file-card.disabled {
    opacity: 0.6;
    background: #f0f0f0;
  }

  .file-header {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }
  .file-enable {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    flex: 1;
    min-width: 0;
  }
  .file-enable input[type="checkbox"] {
    margin: 0;
    accent-color: var(--color-primary);
    flex-shrink: 0;
  }
  .file-name {
    font-weight: 500;
    min-width: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }
  .file-header select {
    padding: 4px 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: white;
    min-width: 120px;
  }

  .file-fields {
    margin-top: 8px;
    padding-left: 24px;
  }

  .no-track-message {
    color: #999;
    font-style: italic;
    padding: 4px 0 0 24px;
  }

  .track-selector {
    margin: 16px 0;
  }
  .track-selector select {
    padding: 4px 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    margin-left: 8px;
    background: white;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 20px;
    border-top: 1px solid #eee;
    flex-shrink: 0;
  }
  .cancel-btn {
    background: transparent;
    border: 1px solid #ddd;
    color: #666;
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
  }
  .cancel-btn:hover {
    background: rgba(0, 0, 0, 0.05);
  }
  .apply-btn {
    background: var(--color-primary);
    color: white;
    border: none;
    padding: 8px 20px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
  }
  .apply-btn:hover {
    background: var(--color-primary-focus);
  }
  .apply-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
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

  .global-fields {
    margin-bottom: 20px;
    padding: 12px;
    background: #f5f5f5;
    border-radius: 6px;
  }
  .global-fields h4 {
    margin: 0 0 8px 0;
    font-size: 14px;
    color: #555;
  }
  .global-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
  }
  .global-header h4 {
    margin: 0;
  }
  .toggle-icon {
    font-size: 14px;
    color: #888;
  }

  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
    margin-bottom: 12px;
  }
  .preset-btn {
    background: #e8e8e8;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.2s;
  }
  .preset-btn:hover {
    background: #d0d0d0;
  }

  /* Dark mode */
  :global(body.dark) .modal-container {
    background: #2d2d2d;
  }
  :global(body.dark) .modal-header {
    border-color: #444;
  }
  :global(body.dark) .modal-header h2 {
    color: #e0e0e0;
  }
  :global(body.dark) .close-btn {
    color: #aaa;
  }
  :global(body.dark) .close-btn:hover {
    color: #fff;
  }
  :global(body.dark) .form-group label {
    color: #aaa;
  }
  :global(body.dark) .form-group select,
  :global(body.dark) .form-group input {
    background: #3d3d3d;
    border-color: #555;
    color: #e0e0e0;
  }
  :global(body.dark) .search-btn {
    background: var(--color-primary-dark);
  }
  :global(body.dark) .search-btn:hover {
    background: var(--color-primary-dark-focus);
  }
  :global(body.dark) .result-item {
    border-color: #444;
  }
  :global(body.dark) .result-item:hover {
    background: #3d3d3d;
  }
  :global(body.dark) .result-item.selected {
    background: var(--color-primary-transparent-dark);
    border-left-color: var(--color-primary-dark);
  }
  :global(body.dark) .result-extra-info {
    color: #aaa;
  }
  :global(body.dark) .metadata-preview {
    border-color: #444;
  }
  :global(body.dark) .metadata-preview h3 {
    color: #e0e0e0;
  }
  :global(body.dark) .extra-info {
    background: var(--color-primary-transparent-dark);
    border-left-color: var(--color-primary-dark);
    color: #ccc;
  }
  :global(body.dark) .field-value {
    color: #ccc;
  }
  :global(body.dark) .batch-container {
    border-color: #444;
  }
  :global(body.dark) .batch-container h3 {
    color: #e0e0e0;
  }
  :global(body.dark) .file-card {
    border-color: #444;
    background: #3d3d3d;
  }
  :global(body.dark) .file-card.disabled {
    background: #2d2d2d;
  }
  :global(body.dark) .file-header select {
    background: #3d3d3d;
    border-color: #555;
    color: #e0e0e0;
  }
  :global(body.dark) .modal-footer {
    border-color: #444;
  }
  :global(body.dark) .cancel-btn {
    border-color: #555;
    color: #aaa;
  }
  :global(body.dark) .cancel-btn:hover {
    background: rgba(255, 255, 255, 0.1);
  }
  :global(body.dark) .apply-btn {
    background: var(--color-primary-dark);
  }
  :global(body.dark) .apply-btn:hover {
    background: var(--color-primary-dark-focus);
  }
  :global(body.dark) .results-list {
    border: 1px solid #555;
  }
  :global(body.dark) .global-fields {
    background: #3d3d3d;
  }
  :global(body.dark) .global-fields h4 {
    color: #aaa;
  }
  :global(body.dark) .toggle-icon {
    color: #aaa;
  }
  :global(body.dark) .preset-btn {
    background: #3d3d3d;
    border-color: #555;
    color: #e0e0e0;
  }
  :global(body.dark) .preset-btn:hover {
    background: #555;
  }
</style>
