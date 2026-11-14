<!-- src/components/MetadataEditor.svelte -->
<script>
  import HoldButton from "./HoldButton.svelte";
  import LyricsEditorModal from "./LRCEditor.svelte";
  import { SvelteSet } from "svelte/reactivity";
  import { tick } from "svelte";

  import {
    toast,
    processEditedLyrics,
    getFieldLabel,
    getFieldDescription,
    settings,
    sanitizeHoldDuration,
    DEFAULT_HOLD_DURATIONS,
    isRemoteImageUrl,
    setCoverFromUrl,
    formatImageDimensions,
    probeImageSize,
    createHold,
  } from "../utils/index.js";

  /**
   * @typedef {Object} MetadataFields
   * @property {string} title
   * @property {string} album
   * @property {string} artist
   * @property {string} albumArtist
   * @property {string} trackNumber
   * @property {string} diskNumber
   * @property {string} date
   * @property {string} genre
   * @property {string} comment
   * @property {string} description
   * @property {string} lyrics
   * @property {string} unsyncedLyrics
   * @property {Record<string, string>} otherFields
   * @property {string | null} picture
   */

  /**
   * @typedef {Object} CustomField
   * @property {string} name
   * @property {string} value
   */

  /**
   * @typedef {Object} Props
   * @property {string} filePath
   */

  /** @type {Props} */
  let { filePath } = $props();

  /** The editor container, for keeping focus inside it when no field is left. */
  let editorRoot = $state(/** @type {HTMLDivElement | null} */ (null));

  // Reactive state for metadata
  /** @type {MetadataFields & Record<string, any>} */
  let metadata = $state({
    title: "",
    album: "",
    artist: "",
    albumArtist: "",
    trackNumber: "",
    diskNumber: "",
    date: "",
    genre: "",
    comment: "",
    description: "",
    lyrics: "",
    unsyncedLyrics: "",
    otherFields: {
      composer: "",
      publisher: "",
    },
    picture: null,
  });

  // UI state
  let otherExpanded = $state(false);
  let customFields = $state(/** @type {CustomField[]} */ ([]));

  // Track which custom field row is being edited.

  // Unsupported files are listed in the tree for inspection only. The API
  // returns ``readOnly`` for them, which disables every editing control.
  let readOnly = $state(false);
  let readOnlyFormat = $state("");

  // Track which field is being edited (by field name)
  /** @type {SvelteSet<string>} */
  let editingFields = new SvelteSet();

  let customFieldEditing = $state(/** @type {boolean[]} */ ([]));

  let applyToSubfolders = $state(false); // false = current folder only, true = include subfolders

  // Hold times come from Settings; sanitize guards against old or hand-edited
  // saved values (missing, non-numeric or out of range).
  const holdApplyDuration = $derived(
    sanitizeHoldDuration(
      $settings.holdApplyDuration,
      DEFAULT_HOLD_DURATIONS.apply,
    ),
  );
  const holdTagDeleteDuration = $derived(
    sanitizeHoldDuration(
      $settings.holdTagDeleteDuration,
      DEFAULT_HOLD_DURATIONS.tagDelete,
    ),
  );

  // ========== KEYBOARD MODEL ==========
  // The editor is made of text fields with action icons, so the icons stay out
  // of the tab order and every action is a shortcut on the focused field:
  //
  //   Enter          apply this field to the file
  //   Ctrl+Enter     HOLD to apply to the folder (progress fills the field)
  //   Ctrl+Delete    HOLD to delete the field (from the file or from the folder
  //                  when "Tag deletion applies to folder" is on)
  //   Alt+ArrowDown  next field        Alt+ArrowUp   previous field
  //   Tab/Shift+Tab  next/previous text field or checkbox
  //
  // Holding matches the mouse hold-to-confirm controls and uses the same
  // configured durations, so a folder-wide change cannot happen by a slip.

  /** Field ids in the order they are rendered, used by Alt+Arrow. */
  let fieldOrder = $derived.by(() => {
    if (readOnly) return [];
    const order = [...mainFields];
    if (otherExpanded) {
      // These are the order the sections render in: the textareas, then the
      // tags from `otherFields`, then the custom rows.
      order.push(...textareaFields);
      order.push(...Object.keys(metadata.otherFields ?? {}));
    }
    for (let i = 0; i < customFields.length; i += 1) {
      order.push(customFieldId(i, "name"), customFieldId(i, "value"));
    }
    return order;
  });

  /**
   * @param {number} index
   * @param {"name" | "value"} part
   */
  function customFieldId(index, part) {
    return `custom-${index}-${part}`;
  }

  /**
   * The control a field id belongs to.
   * @param {string} field
   * @returns {HTMLInputElement | HTMLTextAreaElement | null}
   */
  function fieldControl(field) {
    return /** @type {HTMLInputElement | HTMLTextAreaElement | null} */ (
      document.getElementById(field) ??
        document.querySelector(`[data-field-id="${CSS.escape(field)}"] input`)
    );
  }

  /**
   * The field a control belongs to (a control's id is its field). Passing the
   * keydown target keeps the mapping correct even when focus has not moved yet;
   * without an element the focused control is used (Alt+Arrow navigation).
   * @param {EventTarget | null} [target]
   * @returns {string | null}
   */
  function fieldIdOf(target) {
    const element =
      target instanceof HTMLElement
        ? target
        : document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
    if (!element) return null;
    if (!element.closest(".metadata-editor")) return null;
    // A control's own id is its field; the custom row's data-field-id is only a
    // fallback for controls that have none (it names the row, not one input).
    if (element.id) return element.id;
    const custom = element.closest("[data-field-id]");
    return custom?.getAttribute("data-field-id") ?? null;
  }

  /**
   * Move keyboard focus to one of the editor's fields.
   * @param {string | null} fieldId
   */
  function focusField(fieldId) {
    if (!fieldId) return;
    fieldControl(fieldId)?.focus();
  }

  /**
   * @param {1 | -1} direction
   * @param {EventTarget | null} [target] the control the key was pressed on
   */
  function moveField(direction, target) {
    const order = fieldOrder;
    if (!order.length) return;
    const current = fieldIdOf(target ?? null);
    const index = current ? order.indexOf(current) : -1;
    const next =
      index < 0
        ? direction > 0
          ? 0
          : order.length - 1
        : (index + direction + order.length) % order.length;
    focusField(order[next]);
  }

  /**
   * Keep focus in the editor after a field disappears (a deleted tag unmounts
   * its row). Without this the browser drops focus to `<body>`, where the tree
   * shortcuts take over and a following Delete would remove the whole file.
   * @param {string} field the field that was removed
   */
  async function refocusAfterFieldRemoved(field) {
    if (
      document.activeElement instanceof HTMLElement &&
      document.activeElement.closest(".metadata-editor")
    ) {
      return;
    }
    const order = fieldOrder;
    const index = order.indexOf(field);
    // Prefer the next field, then the previous one, then the first field.
    const target =
      order[index + 1] ?? order[index - 1] ?? order[0] ?? mainFields[0] ?? null;
    await tick();
    focusField(target);
    if (!target) {
      // Nothing editable is left: keep the keyboard in the editor anyway.
      editorRoot?.focus();
    }
  }

  // One hold runs at a time; its progress is drawn on the focused field.
  /** @type {{ field: string, run: () => void } | null} */
  let keyboardHoldTarget = $state(null);
  let keyboardHoldProgress = $state(0);
  let keyboardHoldField = $state(/** @type {string | null} */ (null));

  const keyboardHold = createHold({
    onProgress: (value) => {
      keyboardHoldProgress = value;
    },
    onCancel: () => {
      keyboardHoldProgress = 0;
      keyboardHoldField = null;
    },
    onConfirm: () => {
      const target = keyboardHoldTarget;
      keyboardHoldProgress = 0;
      keyboardHoldField = null;
      target?.run();
    },
  });

  /**
   * Value of a field, read from the control that shows it so a hold applies
   * exactly what the user typed.
   * @param {string} field
   * @returns {string}
   */
  function fieldValue(field) {
    const control = fieldControl(field);
    if (control) return control.value;
    if (field === "lyrics" || field === "unsyncedLyrics") {
      return String(metadata[field] ?? "");
    }
    const own = /** @type {Record<string, unknown>} */ (metadata)[field];
    return typeof own === "string" ? own : "";
  }

  /**
   * Start a hold on the focused field.
   * @param {string} field
   * @param {"folder" | "delete"} kind
   * @param {KeyboardEvent} event
   */
  function startKeyboardHold(field, kind, event) {
    if (readOnly || keyboardHold.isHolding) return;
    if (kind === "folder") {
      keyboardHold.update({ duration: holdApplyDuration });
      keyboardHoldTarget = {
        field,
        run: () => applyToFolder(field, fieldValue(field)),
      };
    } else {
      if (!fieldValue(field)) return;
      keyboardHold.update({ duration: holdTagDeleteDuration });
      keyboardHoldTarget = {
        field,
        run: () =>
          applyDeleteToFolder
            ? deleteFieldFromFolder(field)
            : deleteField(field),
      };
    }
    keyboardHoldField = field;
    keyboardHoldProgress = 0;
    keyboardHold.start(event);
  }

  /** @param {Event} event */
  function endKeyboardHold(event) {
    keyboardHold.cancel(event);
    keyboardHoldTarget = null;
    keyboardHoldProgress = 0;
    keyboardHoldField = null;
  }

  /**
   * Keydown shared by every field. Native behaviour (word-wise arrows,
   * selection with Shift, typing) is left alone.
   * @param {KeyboardEvent} event
   */
  function handleFieldKeydown(event) {
    const field = fieldIdOf(event.target);
    if (!field) return;
    const isTagField = !field.endsWith("-name");

    if (
      event.altKey &&
      (event.key === "ArrowDown" || event.key === "ArrowUp")
    ) {
      event.preventDefault();
      moveField(event.key === "ArrowDown" ? 1 : -1, event.target);
      return;
    }

    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      if (!isTagField) return;
      event.preventDefault();
      // Auto-repeat while the hold is running must not restart it.
      if (event.repeat && keyboardHold.isHolding) return;
      startKeyboardHold(field, "folder", event);
      return;
    }

    if (event.key === "Delete" && (event.ctrlKey || event.metaKey)) {
      if (!isTagField) return;
      event.preventDefault();
      if (event.repeat && keyboardHold.isHolding) return;
      startKeyboardHold(field, "delete", event);
      return;
    }

    // Plain Enter applies the field to this file (unchanged behaviour).
    if (event.key === "Enter" && !event.shiftKey) {
      if (!isTagField) return;
      event.preventDefault();
      const value = fieldValue(field);
      const custom = field.match(/^custom-\d+-value$/);
      if (custom) {
        const index = Number(field.split("-")[1]);
        applyToFile(customFields[index].name, customFields[index].value);
      } else {
        applyToFile(field, value);
      }
    }
  }

  /**
   * Releasing the key that started a hold ends it. The window listener below
   * catches a release outside the field.
   * @param {KeyboardEvent} event
   */
  function handleFieldKeyup(event) {
    if (!keyboardHold.isHolding) return;
    if (event.key === "Enter" || event.key === "Delete") endKeyboardHold(event);
  }

  $effect(() => {
    /** @param {KeyboardEvent | FocusEvent} event */
    const release = (event) => {
      if (event instanceof KeyboardEvent) handleFieldKeyup(event);
      else endKeyboardHold(event);
    };
    window.addEventListener("keyup", release);
    window.addEventListener("blur", release);
    return () => {
      window.removeEventListener("keyup", release);
      window.removeEventListener("blur", release);
    };
  });

  // Derived: filename from path
  let filename = $derived(filePath ? filePath.split(/[\\/]/).pop() : "");

  let pictureEditing = $state(false);
  let pictureFileInput = $state(/** @type {HTMLInputElement | null} */ (null));
  let isUploadingPicture = $state(false);
  let coverSize = $state(
    /** @type {{ width: number, height: number } | null} */ (null),
  );

  const coverDimensions = $derived(
    formatImageDimensions(coverSize?.width, coverSize?.height),
  );

  // Remote cover URL entry. The backend downloads the image through its SSRF
  // guard, so the browser never contacts the remote host.
  let coverUrl = $state("");
  let coverUrlOpen = $state(false);
  let isSavingCoverUrl = $state(false);
  const canApplyCoverUrl = $derived(isRemoteImageUrl(coverUrl.trim()));

  let showFullImage = $state(false);

  // Lyrics modal state
  let lyricsModalContent = $state("");

  let applyDeleteToFolder = $state(false); // false = current file only, true = all files in folder

  // Separate modals for synced and unsynced lyrics
  let showSyncedLyricsModal = $state(false);
  let showUnsyncedLyricsModal = $state(false);

  // Escape closes the unsynced lyrics modal, like the other modals. It is a
  // window listener so it works from the textarea as well.
  $effect(() => {
    if (!showUnsyncedLyricsModal) return;
    /** @param {KeyboardEvent} event */
    const handleEscape = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeUnsyncedLyricsModal();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  });
  let syncedLyricsData = $state(
    /** @type {{ lyrics: string, timestamps: string[] }} */ ({
      lyrics: "",
      timestamps: [],
    }),
  );

  // Track fields that have been edited but not saved
  /** @type {SvelteSet<string>} */
  let dirtyFields = new SvelteSet();

  // Track original values
  let originalMetadata = $state(
    /** @type {(MetadataFields & Record<string, any>) | null} */ (null),
  );

  // Field definitions for main and always‑visible other fields
  const mainFields = [
    "title",
    "album",
    "artist",
    "albumArtist",
    "trackNumber",
    "diskNumber",
    "date",
    "genre",
  ];

  const textareaFields = ["comment", "description"];

  /**
   * @param {string} fieldName
   */
  function startEditing(fieldName) {
    if (readOnly) return;
    editingFields.add(fieldName);
  }

  /**
   * @param {string} fieldName
   */
  function stopEditing(fieldName) {
    // Small delay to allow clicking the icon before blur removes it
    setTimeout(() => {
      if (editingFields.has(fieldName)) {
        editingFields.delete(fieldName);
      }
    }, 150);
  }

  function addCustomField() {
    if (readOnly) return;
    customFields = [...customFields, { name: "", value: "" }];
    customFieldEditing = [...customFieldEditing, false];
  }

  /**
   * @param {string} field
   * @param {string} value
   * @param {boolean} [showToast]
   */
  async function applyToFile(field, value, showToast = true) {
    if (!filePath || readOnly) return;

    try {
      const URL = `/api/metadata/file`;

      const response = await fetch(URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: filePath,
          field: field,
          value: value,
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to update metadata");
      }

      if (showToast) {
        toast.success(`Updated ${field} for this file`);
      }

      // Clear dirty status for this field
      markFieldClean(field);

      // Refresh metadata to show any changes
      await fetchMetadata(filePath);
    } catch (error) {
      console.error("Error updating metadata:", error);
      toast.error(
        `Failed to update: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  /**
   * @param {string} field
   * @param {string} value
   */
  async function applyToFolder(field, value) {
    if (!filePath || readOnly) return;

    // Get the folder path from the file path
    const folderPath = filePath.split("/").slice(0, -1).join("/");

    try {
      // Choose endpoint based on whether to include subfolders
      const endpoint = applyToSubfolders ? "folder" : "folder/current";
      const URL = `/api/metadata/${endpoint}`;

      const requestBody = {
        path: folderPath === "" ? "/" : folderPath, // Send "/" for root
        field: field,
        value: value,
      };

      const response = await fetch(URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to update folder");
      }

      toast.success(result.message || `Updated folder: ${field}`);

      // Refresh current file's metadata in case it was updated
      await fetchMetadata(filePath);
    } catch (error) {
      console.error("Error updating folder:", error);
      toast.error(
        `Failed to update folder: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  /**
   * @param {string} path
   */
  async function fetchMetadata(path) {
    if (!path) return;

    readOnly = false;
    readOnlyFormat = "";
    coverSize = null;

    try {
      const URL = `/api/metadata?path=${encodeURIComponent(path)}`;
      const response = await fetch(URL);

      if (!response.ok) {
        throw new Error(`Failed to fetch metadata: ${response.statusText}`);
      }

      const data = await response.json();

      readOnly = data.readOnly === true || data.supported === false;
      readOnlyFormat = readOnly ? data.format || "" : "";

      // Fields that have dedicated top‑level properties in the component
      const mainFields = [
        "title",
        "album",
        "artist",
        "albumArtist",
        "trackNumber",
        "diskNumber",
        "date",
        "genre",
      ];
      const specialFields = [
        "comment",
        "description",
        "lyrics",
        "unsyncedLyrics",
      ];
      const excludeFields = [
        ...mainFields,
        ...specialFields,
        "picture",
        "customFields",
        "otherFields",
        "readOnly",
        "supported",
        "format",
      ];

      // Start with an empty otherFields object
      /** @type {Record<string, string>} */
      let other = {};

      // Add any top‑level fields that are not in excludeFields (e.g. composer, publisher)
      for (let key in data) {
        if (
          !excludeFields.includes(key) &&
          data[key] &&
          typeof data[key] === "string"
        ) {
          other[key] = data[key];
        }
      }

      // Add all entries from data.customFields (unknown tags)
      if (data.customFields && Array.isArray(data.customFields)) {
        for (let field of data.customFields) {
          other[field.name] = field.value;
        }
      }

      // Merge any existing data.otherFields (for future compatibility)
      if (data.otherFields) {
        other = { ...other, ...data.otherFields };
      }

      // Keep the editor stable: the API returns unknown tags in tag
      // order, so sort the "Other" fields alphabetically by name.
      other = Object.fromEntries(
        Object.entries(other).sort(([a], [b]) =>
          a.localeCompare(b, undefined, { sensitivity: "base" }),
        ),
      );

      const picture = data.picture || null;

      // Update the main metadata object
      metadata = {
        title: data.title || "",
        album: data.album || "",
        artist: data.artist || "",
        albumArtist: data.albumArtist || "",
        trackNumber: data.trackNumber?.toString() || "",
        diskNumber: data.diskNumber?.toString() || "",
        date: data.date?.toString() || "",
        genre: data.genre || "",
        comment: data.comment || "",
        description: data.description || "",
        lyrics: data.lyrics || "",
        unsyncedLyrics: data.unsyncedLyrics || "",
        // @ts-ignore
        otherFields: other,
        picture,
      };

      if (picture) {
        // Tracks in one album usually share the same data URL. The browser can
        // reuse the existing <img> and skip its load event when switching
        // tracks, so resolve the size independently of that event.
        probeImageSize(picture).then((size) => {
          if (size && metadata.picture === picture) {
            coverSize = size;
          }
        });
      }

      customFields = [];

      // After setting metadata, store original values
      originalMetadata = {
        title: data.title || "",
        album: data.album || "",
        artist: data.artist || "",
        albumArtist: data.albumArtist || "",
        trackNumber: data.trackNumber?.toString() || "",
        diskNumber: data.diskNumber?.toString() || "",
        date: data.date?.toString() || "",
        genre: data.genre || "",
        comment: data.comment || "",
        description: data.description || "",
        lyrics: data.lyrics || "",
        unsyncedLyrics: data.unsyncedLyrics || "",
        otherFields: { ...other },
        customFields: [...customFields],
        picture,
      };

      // Clear dirty fields when new metadata loads
      dirtyFields.clear();
    } catch (error) {
      console.error("Error fetching metadata:", error);
      toast.error(
        `Failed to load metadata: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  $effect(() => {
    if (filePath) {
      fetchMetadata(filePath);
    }
  });

  /**
   * @param {File} file
   * @param {boolean} [applyToFolder]
   * @param {boolean} [showToast]
   */
  async function handlePictureUpload(
    file,
    applyToFolder = false,
    showToast = true,
  ) {
    if (!file || !filePath || readOnly) return;

    // Validate file type
    if (!file.type.startsWith("image/")) {
      toast.error("Please select an image file");
      return;
    }

    // Validate file size (e.g., max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Image must be less than 5MB");
      return;
    }

    isUploadingPicture = true;

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append(
        "path",
        applyToFolder
          ? filePath.split("/").slice(0, -1).join("/") // folder path
          : filePath, // file path
      );

      // Choose endpoint based on whether to include subfolders
      const endpoint = applyToFolder
        ? applyToSubfolders
          ? "folder"
          : "folder/current"
        : "file";

      const URL = `/api/metadata/picture/${endpoint}`;

      const response = await fetch(URL, {
        method: "POST",
        body: formData,
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to upload picture");
      }

      if (showToast) {
        toast.success(
          applyToFolder
            ? `Updated cover art for folder (${result.updated} files)`
            : "Updated cover art for this file",
        );
      }

      // Refresh metadata to show new picture
      await fetchMetadata(filePath);
    } catch (error) {
      console.error("Error uploading picture:", error);
      toast.error(
        `Failed to upload picture: ${error instanceof Error ? error.message : String(error)}`,
      );
    } finally {
      isUploadingPicture = false;
      pictureEditing = false;
      // Reset file input
      if (pictureFileInput) {
        pictureFileInput.value = "";
      }
    }
  }

  /**
   * @param {boolean} [applyToFolder]
   */
  function triggerPictureUpload(applyToFolder = false) {
    if (readOnly) return;
    // Reuse the hidden file input, creating it on first use.
    const input = pictureFileInput ?? document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.style.display = "none";
    if (!input.isConnected) document.body.appendChild(input);

    /** @param {Event} e */
    input.onchange = (e) => {
      const file = /** @type {HTMLInputElement} */ (e.target).files?.[0];
      if (file) {
        handlePictureUpload(file, applyToFolder);
      }
    };
    pictureFileInput = input;

    input.click();
  }

  function closeCoverUrl() {
    if (isSavingCoverUrl) return;
    coverUrlOpen = false;
    coverUrl = "";
  }

  /**
   * @param {boolean} [toFolder]
   */
  async function applyCoverUrl(toFolder = false) {
    if (!filePath || readOnly || isSavingCoverUrl) return;

    const url = coverUrl.trim();
    if (!isRemoteImageUrl(url)) {
      toast.warning("Enter a full http(s) image URL");
      return;
    }

    const folderPath = filePath.split("/").slice(0, -1).join("/");
    isSavingCoverUrl = true;
    try {
      const result = await setCoverFromUrl(
        toFolder ? folderPath : filePath,
        url,
        {
          toFolder,
          recursive: toFolder && applyToSubfolders,
        },
      );

      toast.success(
        result?.message ||
          (toFolder
            ? `Updated cover art for folder (${result?.updated ?? 0} files)`
            : "Updated cover art from URL"),
      );
      coverUrlOpen = false;
      coverUrl = "";

      if (toFolder) {
        window.dispatchEvent(new CustomEvent("refreshFileTree"));
      }
      await fetchMetadata(filePath);
    } catch (error) {
      console.error("Error setting cover from URL:", error);
      toast.error(
        `Failed to set cover art: ${error instanceof Error ? error.message : String(error)}`,
      );
    } finally {
      isSavingCoverUrl = false;
    }
  }

  $effect(() => {
    // A different file means any half-typed URL no longer applies.
    filePath;
    coverUrlOpen = false;
    coverUrl = "";
  });

  /**
   * @param {string} field
   */
  async function deleteField(field) {
    if (!filePath || !field || readOnly) return;

    try {
      const URL = `/api/metadata/field/delete`;

      const response = await fetch(URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: filePath,
          field: field,
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to delete field");
      }

      toast.success(`Deleted ${field} from file`);

      // Refresh metadata to reflect changes
      await fetchMetadata(filePath);

      // Clear editing state
      if (editingFields.has(field)) {
        editingFields.delete(field);
      }
      await refocusAfterFieldRemoved(field);
    } catch (error) {
      console.error("Error deleting field:", error);
      toast.error(
        `Failed to delete: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  async function deleteCoverArt() {
    if (!filePath || readOnly) return;

    try {
      const URL = `/api/metadata/picture/delete`;

      const response = await fetch(URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: filePath,
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to delete cover art");
      }

      toast.success("Deleted cover art from file");

      // Refresh metadata to reflect changes
      await fetchMetadata(filePath);
    } catch (error) {
      console.error("Error deleting cover art:", error);
      toast.error(
        `Failed to delete cover art: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  /**
   * @param {Event} event
   */
  function handleCoverLoad(event) {
    const image = /** @type {HTMLImageElement} */ (event.currentTarget);
    if (image.naturalWidth > 0 && image.naturalHeight > 0) {
      coverSize = {
        width: image.naturalWidth,
        height: image.naturalHeight,
      };
    }
  }

  function openFullImage() {
    if (metadata.picture) {
      showFullImage = true;
    }
  }

  function closeFullImage() {
    showFullImage = false;
  }

  async function saveCoverAsFile() {
    if (!filePath || !metadata.picture) return;

    try {
      const URL = `/api/metadata/picture/save-as-file`;

      const response = await fetch(URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: filePath,
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to save cover art");
      }

      toast.success(result.message);

      // Dispatch event to refresh the file tree
      const event = new CustomEvent("refreshFileTree");
      window.dispatchEvent(event);
    } catch (error) {
      console.error("Error saving cover art:", error);
      toast.error(
        `Failed to save: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  function openSyncedLyricsModal() {
    // For synced lyrics, we need to parse timestamps
    if (metadata.lyrics) {
      const result = processEditedLyrics(metadata.lyrics);
      syncedLyricsData = {
        lyrics: result.text,
        timestamps: result.timestamps,
      };
    } else {
      syncedLyricsData = {
        lyrics: "",
        timestamps: [],
      };
    }
    showSyncedLyricsModal = true;
  }

  function openUnsyncedLyricsModal() {
    lyricsModalContent = metadata.unsyncedLyrics || "";
    showUnsyncedLyricsModal = true;
  }

  function closeUnsyncedLyricsModal() {
    showUnsyncedLyricsModal = false;
  }

  async function saveUnsyncedLyrics() {
    const field = "unsyncedLyrics";

    // Update local state
    metadata.unsyncedLyrics = lyricsModalContent;

    // Save to file
    await applyToFile(field, lyricsModalContent);

    // Close modal
    closeUnsyncedLyricsModal();
  }

  // Handle save from synced lyrics modal
  /**
   * @param {{ lyrics: string, timestamps: string[], synchronizedLyrics: string | null, hasTimestamps: boolean }} data
   */
  async function handleSyncedLyricsSave(data) {
    const field = "lyrics";

    // If nothing was actually synced, write the plain text
    // (FLAC/OGG/Opus/M4A lyrics fields accept both LRC and plain text).
    // Otherwise write the LRC-formatted string.
    const value =
      (data.hasTimestamps ? data.synchronizedLyrics : data.lyrics) ?? "";

    metadata.lyrics = value;
    // Save to file
    await applyToFile(field, value);

    // Close modal
    showSyncedLyricsModal = false;
  }

  /**
   * @param {Event} e
   */
  function stopPropagation(e) {
    e.stopPropagation();
  }

  async function applyAllChanges() {
    if (!filePath || readOnly) return;

    try {
      // Collect all fields that have values
      const updates = [];

      // Main fields
      for (const field of mainFields) {
        if (metadata[field] && metadata[field].trim() !== "") {
          updates.push({ field, value: metadata[field] });
        }
      }

      // Textarea fields
      for (const field of textareaFields) {
        if (metadata[field] && metadata[field].trim() !== "") {
          updates.push({ field, value: metadata[field] });
        }
      }

      // Other fields
      for (const [key, value] of Object.entries(metadata.otherFields || {})) {
        if (value && value.trim() !== "") {
          updates.push({ field: key, value });
        }
      }

      // Custom fields
      for (const field of customFields) {
        if (
          field.name &&
          field.name.trim() !== "" &&
          field.value &&
          field.value.trim() !== ""
        ) {
          updates.push({ field: field.name, value: field.value });
        }
      }

      if (updates.length === 0 && !metadata.picture) {
        toast.info("No changes to apply");
        return;
      }

      // Apply all updates
      for (const update of updates) {
        await applyToFile(update.field, update.value, false);
      }

      // Handle picture if present
      if (metadata.picture && metadata.picture.startsWith("data:")) {
        // Convert data URL to file and upload
        const response = await fetch(metadata.picture);
        const blob = await response.blob();
        const file = new File([blob], "cover.jpg", { type: blob.type });
        await handlePictureUpload(file, false, false);
      }

      // Clear all dirty statuses
      markAllClean();

      toast.success("All changes applied successfully");
    } catch (error) {
      console.error("Error applying all changes:", error);
      toast.error(
        `Failed to apply all changes: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  /**
   * @param {string} field
   */
  async function deleteFieldFromFolder(field) {
    if (!filePath || !field || readOnly) return;

    // Get the folder path from the file path
    const folderPath = filePath.split("/").slice(0, -1).join("/") || "/";

    try {
      // Same endpoint but with folder path and recursive flag
      const URL = `/api/metadata/field/delete`;

      const response = await fetch(URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: folderPath, // Send folder path instead of file path
          field: field,
          recursive: applyToSubfolders, // Add recursive flag
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to delete field from folder");
      }

      toast.success(
        result.message || `Deleted "${field}" from files in folder`,
      );

      // Refresh current file's metadata in case it was updated
      await fetchMetadata(filePath);

      // Clear editing state
      if (editingFields.has(field)) {
        editingFields.delete(field);
      }
      await refocusAfterFieldRemoved(field);
    } catch (error) {
      console.error("Error deleting field from folder:", error);
      toast.error(
        `Failed to delete from folder: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // Mark field as dirty by comparing with original value
  /**
   * @param {string} fieldName
   * @param {string} newValue
   */
  function trackChange(fieldName, newValue) {
    if (!originalMetadata) return;
    // Get the original value
    let originalValue;

    // Handle different field types
    if (mainFields.includes(fieldName) || textareaFields.includes(fieldName)) {
      originalValue = originalMetadata?.[fieldName] || "";
    } else if (fieldName in metadata.otherFields) {
      originalValue = originalMetadata?.otherFields?.[fieldName] || "";
    } else {
      originalValue = originalMetadata?.[fieldName] || "";
    }

    // Compare with original value
    if (newValue !== originalValue) {
      dirtyFields.add(fieldName);
    } else {
      dirtyFields.delete(fieldName);
    }
  }

  // Clear dirty status after saving
  /**
   * @param {string} fieldName
   */
  function markFieldClean(fieldName) {
    dirtyFields.delete(fieldName);
  }

  // Clear all dirty statuses
  function markAllClean() {
    dirtyFields.clear();
  }

  /**
   * @param {Event} e
   */
  function handleRefreshMetadata(e) {
    const refreshedPath = /** @type {CustomEvent<{ path?: string }>} */ (e)
      .detail?.path;
    if (!refreshedPath || !filePath) {
      fetchMetadata(filePath);
      return;
    }
    // Refresh if the selected file itself was updated, or if it lives inside a folder that was updated.
    if (
      refreshedPath === filePath ||
      filePath.startsWith(refreshedPath + "/")
    ) {
      fetchMetadata(filePath);
    }
  }

  $effect(() => {
    window.addEventListener("refreshMetadata", handleRefreshMetadata);
    return () =>
      window.removeEventListener("refreshMetadata", handleRefreshMetadata);
  });
</script>

<div
  class="metadata-editor"
  class:readonly={readOnly}
  bind:this={editorRoot}
  tabindex="-1"
>
  {#if !readOnly}
    <div class="operation-controls">
      <label
        class="checkbox-label"
        title="When enabled, folder operations will include subfolders"
      >
        <input type="checkbox" bind:checked={applyToSubfolders} />
        <span>Recursive</span>
      </label>
      <label
        class="checkbox-label"
        title="When enabled, tag deletetion operations will apply to all files in folder"
      >
        <input type="checkbox" bind:checked={applyDeleteToFolder} />
        <span>Tag deletion applies to folder</span>
      </label>
    </div>
  {/if}

  <!-- Filename badge -->
  <div class="editor-header">
    <div class="filename-badge">{filename}</div>
  </div>

  {#if readOnly}
    <div class="readonly-banner" role="note">
      <span class="readonly-badge">Read-only</span>
      <span>
        {#if readOnlyFormat}
          {readOnlyFormat} files are not supported for tag editing.
        {:else}
          This file type is not supported for tag editing.
        {/if}
        You can still rename, download or delete the file from the tree.
      </span>
    </div>
  {/if}

  <div class="cover-art-container">
    <div class="cover-art" class:editing={pictureEditing}>
      {#if metadata.picture}
        <img
          src={metadata.picture}
          alt="Cover Art"
          style="width:100%; height:100%; object-fit: cover;"
          onload={handleCoverLoad}
        />
      {:else}
        <!-- Cover art placeholder -->
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 200 200"
          preserveAspectRatio="none"
        >
          <rect width="200" height="200" fill="#e0e0e0" />
          <text
            x="50%"
            y="50%"
            dominant-baseline="middle"
            text-anchor="middle"
            fill="#999"
            font-size="14"
          >
            Album Art
          </text>
        </svg>
      {/if}

      <div
        role="img"
        class="cover-art-overlay"
        onmouseenter={() => (pictureEditing = true)}
        onmouseleave={() => (pictureEditing = false)}
      >
        {#if pictureEditing && !isUploadingPicture}
          <!-- Expand icon in top-left corner -->
          <div class="cover-art-expand">
            <button
              class="icon-btn expand-btn"
              title="View full size"
              onclick={openFullImage}
              disabled={!metadata.picture}
            >
              <svg
                viewBox="0 0 20 20"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                class="svelte-1n4vb3j"
                width="20"
                height="20"
                ><path
                  d="M7 3H4.5C4 3 4 3 4 3.5V6M17 6V4C17 3 17 3 16 3H14M14 16H16C17 16 17 16 17 15V13M4 13V15C4 16 4 16 5 16H7"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                ></path></svg
              >
            </button>
          </div>
          {#if !readOnly}
            <div class="cover-art-actions">
              <button
                class="icon-btn"
                tabindex={-1}
                title="Set cover art from URL"
                onclick={() => (coverUrlOpen = !coverUrlOpen)}
                disabled={isUploadingPicture || isSavingCoverUrl}
                aria-expanded={coverUrlOpen}
              >
                <!-- Link icon - remote URL -->
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
                >
                  <path
                    d="M10 13a5 5 0 0 0 7.07 0l2.12-2.12a5 5 0 0 0-7.07-7.07L11 5"
                  />
                  <path
                    d="M14 11a5 5 0 0 0-7.07 0L4.81 13.12a5 5 0 0 0 7.07 7.07L13 19"
                  />
                </svg>
              </button>
              <button
                class="icon-btn"
                tabindex={-1}
                title="Upload cover art for this file only"
                onclick={() => triggerPictureUpload(false)}
                disabled={isUploadingPicture}
              >
                <!-- File icon - matches other fields -->
                <svg
                  width="14"
                  height="16"
                  viewBox="0 0 14 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                    fill="currentColor"
                    fill-opacity="0.7"
                  />
                  <path
                    d="M10 1L12 3H10V1Z"
                    fill="currentColor"
                    fill-opacity="0.7"
                  />
                </svg>
              </button>
              <HoldButton
                tabindex={-1}
                variant="icon"
                duration={holdApplyDuration}
                onConfirm={() => triggerPictureUpload(true)}
                disabled={isUploadingPicture}
                title={applyToSubfolders
                  ? "Hold to apply to all files in folder (including subfolders)"
                  : "Hold to apply to all files in folder (same level only)"}
                class="cover-art-icon"
              >
                <!-- Folder icon SVG -->
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                    fill="currentColor"
                    fill-opacity="0.9"
                  />
                </svg>
              </HoldButton>
              {#if metadata.picture}
                <HoldButton
                  tabindex={-1}
                  variant="icon"
                  duration={holdTagDeleteDuration}
                  onConfirm={deleteCoverArt}
                  disabled={isUploadingPicture}
                  title="Hold to delete cover art"
                  class="delete-btn cover-art-icon"
                >
                  <!-- Trash can icon -->
                  <svg
                    width="14"
                    height="16"
                    viewBox="0 0 14 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M1 4H13M9 2H5M5 7V12M9 7V12M2 4L2.5 13.5C2.5 14.3284 3.17157 15 4 15H10C10.8284 15 11.5 14.3284 11.5 13.5L12 4"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                    />
                  </svg>
                </HoldButton>
                <button
                  class="icon-btn"
                  tabindex={-1}
                  title="Save as cover.*"
                  onclick={saveCoverAsFile}
                  disabled={isUploadingPicture || !metadata.picture}
                >
                  <!-- Save icon -->
                  <svg
                    width="14"
                    height="16"
                    viewBox="0 0 14 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M7 2V11M7 11L10 8M7 11L4 8"
                      stroke="currentColor"
                      stroke-width="1.8"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M2 14H12"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                    />
                  </svg>
                </button>
              {/if}
            </div>
          {/if}
        {:else if isUploadingPicture}
          <div class="uploading-indicator">
            <span>Uploading...</span>
          </div>
        {/if}
      </div>

      {#if coverDimensions}
        <span class="cover-art-size">{coverDimensions}</span>
      {/if}
    </div>
  </div>

  {#if coverUrlOpen && !readOnly}
    <div class="cover-url-field">
      <label for="cover-url-input">Cover art URL</label>
      <div class="cover-url-input-wrapper">
        <input
          id="cover-url-input"
          type="url"
          bind:value={coverUrl}
          placeholder={isSavingCoverUrl
            ? "Applying…"
            : "https://example.com/cover.jpg"}
          aria-label="Cover art image URL"
          disabled={isSavingCoverUrl}
          onkeydown={(e) => {
            if (e.key === "Enter") applyCoverUrl(false);
            if (e.key === "Escape") closeCoverUrl();
          }}
        />
        <div class="cover-url-actions">
          <button
            class="icon-btn"
            tabindex={-1}
            title="Apply this URL to the current file"
            onclick={() => applyCoverUrl(false)}
            disabled={!canApplyCoverUrl || isSavingCoverUrl}
          >
            <!-- File icon - matches the upload action -->
            <svg
              width="14"
              height="16"
              viewBox="0 0 14 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                fill="currentColor"
                fill-opacity="0.7"
              />
              <path
                d="M10 1L12 3H10V1Z"
                fill="currentColor"
                fill-opacity="0.7"
              />
            </svg>
          </button>
          <HoldButton
            tabindex={-1}
            variant="icon"
            duration={holdApplyDuration}
            onConfirm={() => applyCoverUrl(true)}
            disabled={!canApplyCoverUrl || isSavingCoverUrl}
            title={applyToSubfolders
              ? "Hold to apply this URL to all files in folder (including subfolders)"
              : "Hold to apply this URL to all files in folder (same level only)"}
            class="cover-url-icon"
          >
            <!-- Folder icon - matches the folder upload action -->
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                fill="currentColor"
                fill-opacity="0.9"
              />
            </svg>
          </HoldButton>
        </div>
      </div>
    </div>
  {/if}

  <!-- Main fields (all text inputs) -->
  <div class="fields-stack">
    {#each mainFields as field (field)}
      {@const value = metadata[field]}
      {@const isDirty = dirtyFields.has(field)}
      <div
        class="field"
        class:editing={editingFields.has(field)}
        class:dirty={isDirty}
      >
        <label for={field} title={getFieldDescription(field) || undefined}>
          {getFieldLabel(field)}
        </label>
        <div class="input-wrapper">
          <input
            type="text"
            id={field}
            value={metadata[field]}
            oninput={(e) => {
              // @ts-ignore
              metadata[field] = e.target.value;
              trackChange(field, metadata[field]);
            }}
            onfocus={() => startEditing(field)}
            onblur={() => stopEditing(field)}
            onkeydown={handleFieldKeydown}
            placeholder={field}
            readonly={readOnly}
          />
          {#if keyboardHoldField === field}
            <div
              class="hold-progress"
              aria-hidden="true"
              style="--progress: {keyboardHoldProgress};"
            ></div>
          {/if}
          {#if editingFields.has(field)}
            <div class="field-actions">
              <!-- Delete button -->
              {#if metadata[field]}
                <HoldButton
                  tabindex={-1}
                  variant="icon"
                  duration={holdTagDeleteDuration}
                  onConfirm={() => {
                    if (applyDeleteToFolder) {
                      deleteFieldFromFolder(field);
                    } else {
                      deleteField(field);
                    }
                  }}
                  title={applyDeleteToFolder
                    ? "Hold to delete this field from all files in folder"
                    : "Hold to delete this field from current file"}
                  class="delete-btn"
                >
                  <!-- Trash can icon -->
                  <svg
                    width="14"
                    height="16"
                    viewBox="0 0 14 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M1 4H13M9 2H5M5 7V12M9 7V12M2 4L2.5 13.5C2.5 14.3284 3.17157 15 4 15H10C10.8284 15 11.5 14.3284 11.5 13.5L12 4"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                    />
                  </svg>
                </HoldButton>
              {/if}
              <!-- File button -->
              <button
                class="icon-btn"
                tabindex={-1}
                title="Apply to this file only"
                onclick={() => applyToFile(field, value)}
              >
                <!-- File icon SVG -->
                <svg
                  width="14"
                  height="16"
                  viewBox="0 0 14 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                    fill="currentColor"
                    fill-opacity="0.7"
                  />
                  <path
                    d="M10 1L12 3H10V1Z"
                    fill="currentColor"
                    fill-opacity="0.7"
                  />
                </svg>
              </button>
              <!-- Folder button -->
              <HoldButton
                tabindex={-1}
                variant="icon"
                duration={holdApplyDuration}
                onConfirm={() => applyToFolder(field, metadata[field])}
                title={applyToSubfolders
                  ? "Hold to apply to all files in folder (including subfolders)"
                  : "Hold to apply to all files in folder (same level only)"}
              >
                <!-- Folder icon SVG -->
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                    fill="currentColor"
                    fill-opacity="0.9"
                  />
                </svg>
              </HoldButton>
            </div>
          {/if}
        </div>
      </div>
    {/each}
  </div>

  <!-- Lyrics action buttons -->
  {#if !readOnly}
    <div class="lyrics-actions">
      <button class="action-btn" onclick={openSyncedLyricsModal}>
        Edit synced lyrics
      </button>
      <button class="action-btn" onclick={openUnsyncedLyricsModal}>
        Edit unsynced lyrics
      </button>
    </div>
  {/if}

  <!-- Other section (collapsible) -->
  <div class="other-section">
    <button
      class="collapse-toggle"
      onclick={() => (otherExpanded = !otherExpanded)}
    >
      {otherExpanded ? "X" : "▶"} Other
    </button>

    {#if otherExpanded}
      <div class="other-fields">
        <!-- Textarea fields (comment, description) -->
        {#each textareaFields as field (field)}
          {@const value = metadata[field]}
          {@const isDirty = dirtyFields.has(field)}
          <div
            class="field"
            class:editing={editingFields.has(field)}
            class:dirty={isDirty}
          >
            <label for={field} title={getFieldDescription(field) || undefined}>
              {getFieldLabel(field)}
            </label>
            <div class="input-wrapper">
              <textarea
                id={field}
                value={metadata[field]}
                oninput={(e) => {
                  // @ts-ignore
                  metadata[field] = e.target.value;
                  trackChange(field, metadata[field]);
                }}
                onfocus={() => startEditing(field)}
                onblur={() => stopEditing(field)}
                onkeydown={handleFieldKeydown}
                placeholder={field}
                rows="2"
                readonly={readOnly}></textarea>
              {#if keyboardHoldField === field}
                <div
                  class="hold-progress"
                  aria-hidden="true"
                  style="--progress: {keyboardHoldProgress};"
                ></div>
              {/if}
              {#if editingFields.has(field)}
                <div class="field-actions textarea-actions">
                  <!-- Delete button -->
                  {#if metadata[field]}
                    <HoldButton
                      tabindex={-1}
                      variant="icon"
                      duration={holdTagDeleteDuration}
                      onConfirm={() => {
                        if (applyDeleteToFolder) {
                          deleteFieldFromFolder(field);
                        } else {
                          deleteField(field);
                        }
                      }}
                      title={applyDeleteToFolder
                        ? "Hold to delete this field from all files in folder"
                        : "Hold to delete this field from current file"}
                      class="delete-btn"
                    >
                      <!-- Trash can icon -->
                      <svg
                        width="14"
                        height="16"
                        viewBox="0 0 14 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M1 4H13M9 2H5M5 7V12M9 7V12M2 4L2.5 13.5C2.5 14.3284 3.17157 15 4 15H10C10.8284 15 11.5 14.3284 11.5 13.5L12 4"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                        />
                      </svg>
                    </HoldButton>
                  {/if}
                  <!-- File button -->
                  <button
                    class="icon-btn"
                    tabindex={-1}
                    onclick={() => applyToFile(field, value)}
                  >
                    <!-- File icon SVG -->
                    <svg
                      width="14"
                      height="16"
                      viewBox="0 0 14 16"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                        fill="currentColor"
                        fill-opacity="0.7"
                      />
                      <path
                        d="M10 1L12 3H10V1Z"
                        fill="currentColor"
                        fill-opacity="0.7"
                      />
                    </svg>
                  </button>
                  <!-- Folder button -->
                  <HoldButton
                    tabindex={-1}
                    variant="icon"
                    duration={holdApplyDuration}
                    onConfirm={() => applyToFolder(field, value)}
                    title={applyToSubfolders
                      ? "Hold to apply to all files in folder (including subfolders)"
                      : "Hold to apply to all files in folder (same level only)"}
                  >
                    <!-- Folder icon SVG -->
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                        fill="currentColor"
                        fill-opacity="0.9"
                      />
                    </svg>
                  </HoldButton>
                </div>
              {/if}
            </div>
          </div>
        {/each}

        <!-- Other fields from metadata.otherFields -->
        {#each Object.entries(metadata.otherFields || {}) as [key, value] (key)}
          {@const isDirty = dirtyFields.has(key)}
          <div class="field" class:dirty={isDirty}>
            <label for={key} title={getFieldDescription(key) || undefined}>
              {getFieldLabel(key)}
            </label>
            <div class="input-wrapper">
              <input
                type="text"
                id={key}
                value={metadata.otherFields[key]}
                oninput={(e) => {
                  // @ts-ignore
                  metadata.otherFields[key] = e.target.value;
                  trackChange(key, metadata.otherFields[key]);
                }}
                onfocus={() => startEditing(key)}
                onblur={() => stopEditing(key)}
                onkeydown={handleFieldKeydown}
                readonly={readOnly}
              />
              {#if keyboardHoldField === key}
                <div
                  class="hold-progress"
                  aria-hidden="true"
                  style="--progress: {keyboardHoldProgress};"
                ></div>
              {/if}
              {#if editingFields.has(key)}
                <div class="field-actions">
                  <!-- Delete button -->
                  {#if value}
                    <HoldButton
                      tabindex={-1}
                      variant="icon"
                      duration={holdTagDeleteDuration}
                      onConfirm={() => {
                        if (applyDeleteToFolder) {
                          deleteFieldFromFolder(key);
                        } else {
                          deleteField(key);
                        }
                      }}
                      title={applyDeleteToFolder
                        ? "Hold to delete this field from all files in folder"
                        : "Hold to delete this field from current file"}
                      class="delete-btn"
                    >
                      <!-- Trash can icon -->
                      <svg
                        width="14"
                        height="16"
                        viewBox="0 0 14 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M1 4H13M9 2H5M5 7V12M9 7V12M2 4L2.5 13.5C2.5 14.3284 3.17157 15 4 15H10C10.8284 15 11.5 14.3284 11.5 13.5L12 4"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                        />
                      </svg>
                    </HoldButton>
                  {/if}
                  <!-- File button -->
                  <button
                    class="icon-btn"
                    tabindex={-1}
                    onclick={() => applyToFile(key, value)}
                  >
                    <!-- File icon SVG -->
                    <svg
                      width="14"
                      height="16"
                      viewBox="0 0 14 16"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                        fill="currentColor"
                        fill-opacity="0.7"
                      />
                      <path
                        d="M10 1L12 3H10V1Z"
                        fill="currentColor"
                        fill-opacity="0.7"
                      />
                    </svg>
                  </button>
                  <!-- Folder button -->
                  <HoldButton
                    tabindex={-1}
                    variant="icon"
                    duration={holdApplyDuration}
                    onConfirm={() => applyToFolder(key, value)}
                    title={applyToSubfolders
                      ? "Hold to apply to all files in folder (including subfolders)"
                      : "Hold to apply to all files in folder (same level only)"}
                  >
                    <!-- Folder icon SVG -->
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                        fill="currentColor"
                        fill-opacity="0.9"
                      />
                    </svg>
                  </HoldButton>
                </div>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Add new field button -->
  {#if !readOnly}
    <button class="add-field-btn" onclick={addCustomField}>
      + Add new field
    </button>
  {/if}

  <!-- Custom fields added by user -->
  {#each customFields as field, i (field)}
    <div
      class="field custom"
      class:editing={customFieldEditing[i]}
      data-field-id={customFieldId(i, "value")}
      onfocusin={() => (customFieldEditing[i] = true)}
      onfocusout={(e) => {
        // @ts-ignore
        if (!e.currentTarget.contains(e.relatedTarget)) {
          customFieldEditing[i] = false;
        }
      }}
    >
      <!-- Field name input -->
      <input
        type="text"
        id={customFieldId(i, "name")}
        placeholder="Field name"
        bind:value={customFields[i].name}
        onkeydown={handleFieldKeydown}
      />

      <!-- Value row: input and icons -->
      <div class="value-row">
        <input
          type="text"
          id={customFieldId(i, "value")}
          placeholder="Value"
          bind:value={customFields[i].value}
          onkeydown={handleFieldKeydown}
        />
        {#if keyboardHoldField === customFieldId(i, "value")}
          <div
            class="hold-progress"
            aria-hidden="true"
            style="--progress: {keyboardHoldProgress};"
          ></div>
        {/if}
        {#if customFieldEditing[i]}
          <div class="field-actions" style="position: static; transform: none;">
            <!-- File button -->
            <button
              class="icon-btn"
              tabindex={-1}
              title="Apply to this file only"
              onclick={() =>
                applyToFile(customFields[i].name, customFields[i].value)}
            >
              <!-- File icon SVG -->
              <svg
                width="14"
                height="16"
                viewBox="0 0 14 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                  fill="currentColor"
                  fill-opacity="0.7"
                />
                <path
                  d="M10 1L12 3H10V1Z"
                  fill="currentColor"
                  fill-opacity="0.7"
                />
              </svg>
            </button>
            <!-- Folder button -->
            <HoldButton
              tabindex={-1}
              variant="icon"
              duration={holdApplyDuration}
              onConfirm={() =>
                applyToFolder(customFields[i].name, customFields[i].value)}
              title={applyToSubfolders
                ? "Hold to apply to all files in folder (including subfolders)"
                : "Hold to apply to all files in folder (same level only)"}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                  fill="currentColor"
                  fill-opacity="0.9"
                />
              </svg>
            </HoldButton>
          </div>
        {/if}
      </div>
    </div>
  {/each}

  <!-- Lyrics Modal -->
  {#if showUnsyncedLyricsModal}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="lyrics-modal-overlay" onclick={closeUnsyncedLyricsModal}>
      <div class="lyrics-modal" onclick={stopPropagation}>
        <div class="lyrics-modal-header">
          <h3>Edit Unsynced Lyrics</h3>
          <button
            title="Close"
            class="modal-close-btn"
            onclick={closeUnsyncedLyricsModal}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M12 4L4 12M4 4L12 12"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>

        <div class="lyrics-modal-content">
          <!-- svelte-ignore a11y_autofocus -->
          <textarea
            bind:value={lyricsModalContent}
            placeholder="Enter unsynced lyrics here..."
            class="lyrics-textarea"
            autofocus></textarea>
        </div>

        <div class="lyrics-modal-footer">
          <button class="cancel-btn" onclick={closeUnsyncedLyricsModal}>
            Cancel
          </button>
          <div class="save-actions">
            <button
              class="save-btn"
              onclick={saveUnsyncedLyrics}
              title="Save to this file only"
            >
              <svg
                width="14"
                height="16"
                viewBox="0 0 14 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                  fill="currentColor"
                  fill-opacity="0.7"
                />
                <path
                  d="M10 1L12 3H10V1Z"
                  fill="currentColor"
                  fill-opacity="0.7"
                />
              </svg>
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Full-size image modal -->
  {#if showFullImage && metadata.picture}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div role="img" class="full-image-modal" onclick={closeFullImage}>
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="modal-content" onclick={(e) => e.stopPropagation()}>
        <button class="modal-close-btn" title="Close" onclick={closeFullImage}>
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
        <img src={metadata.picture} alt="Full size cover art" />
        {#if coverDimensions}
          <p class="full-image-dimensions">{coverDimensions}</p>
        {/if}
      </div>
    </div>
  {/if}
  <div class="batch-actions">
    <button class="batch-apply-btn" onclick={applyAllChanges}>
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M13 4L6 11L3 8"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      Apply All Changes
    </button>
  </div>
  <LyricsEditorModal
    isOpen={showSyncedLyricsModal}
    onClose={() => (showSyncedLyricsModal = false)}
    {filePath}
    initialLyrics={syncedLyricsData.lyrics}
    initialTimestamps={syncedLyricsData.timestamps}
    trackInfo={{
      title: metadata.title,
      artist: metadata.artist,
      album: metadata.album,
    }}
    onSave={handleSyncedLyricsSave}
  />
</div>

<style>
  .metadata-editor {
    height: 100%;
    overflow-y: auto;
    padding: 16px;
    box-sizing: border-box;
  }

  input:focus,
  textarea:focus {
    outline: none;
    border-color: var(
      --color-primary
    ) !important; /* !important to override any existing border-color */
  }

  .filename-badge {
    font-size: 13px;
    color: #888;
    margin-bottom: 16px;
    text-align: center;
    max-width: 100%;
    word-break: break-all;
    white-space: normal; /* Allow wrapping */
    overflow: visible; /* Don't truncate */
    background: rgba(0, 0, 0, 0.03);
    padding: 4px 8px;
    border-radius: 4px;
  }

  /* Stack fields vertically */
  .fields-stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 24px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
    position: relative;
    padding: 2px 0; /* Add small padding for hover area */
  }

  .field label {
    font-size: 12px;
    font-weight: 500;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .input-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    flex: 1; /* Take remaining space */
    min-width: 0; /* Prevent overflow */
    width: 100%;
  }

  /* Progress of a held shortcut (Ctrl+Enter / Ctrl+Delete) on the field. It
     sits above the input and never takes pointer events. */
  .hold-progress {
    position: absolute;
    inset: 0;
    z-index: 3;
    pointer-events: none;
    border-radius: 4px;
    background: linear-gradient(
      to right,
      var(--color-primary-transparent) calc(var(--progress) * 100%),
      transparent 0
    );
    box-shadow: inset 0 0 0 1px var(--color-primary);
  }

  /* Base input styles */
  .input-wrapper input,
  .input-wrapper textarea,
  .field.custom input {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
    background: white;
    box-sizing: border-box;
  }

  /* Make space for icons when editing a standard field */
  .field.editing input,
  .field.editing textarea {
    padding-right: 70px;
  }

  .input-wrapper textarea {
    resize: vertical;
    min-height: 60px;
  }

  /* Adjust padding when editing to make room for action buttons */
  .field.editing .input-wrapper input,
  .field.editing .input-wrapper textarea {
    padding-right: 70px;
  }

  .field-actions {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    gap: 2px;
    background: white;
    padding: 2px;
    border-radius: 4px;
    z-index: 10;
  }

  /* For textareas, align icons to the top */
  .textarea-actions {
    top: 12px;
    transform: none;
  }

  .icon-btn {
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

  .icon-btn:hover {
    background: rgba(0, 0, 0, 0.1);
    color: var(--color-primary);
  }

  .other-section {
    margin-top: 20px;
    border-top: 1px solid #eee;
    padding-top: 16px;
  }

  .collapse-toggle {
    background: none;
    border: none;
    color: var(--color-primary);
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    padding: 4px 0;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .other-fields {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Custom field container */
  .field.custom {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 16px;
    margin-bottom: 16px;
    width: 100%;
  }

  .add-field-btn {
    background: transparent;
    border: 1px dashed var(--color-primary);
    color: var(--color-primary);
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    margin-top: 20px;
    width: 100%;
  }

  .add-field-btn:hover {
    background: var(--color-primary-transparent);
  }

  /* Value row: flex container for input + icons */
  .value-row {
    display: flex;
    align-items: center;
    gap: 4px;
    width: 100%;
  }

  /* Value input takes all available space */
  .value-row input {
    flex: 1;
    min-width: 0;
  }

  .lyrics-actions {
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }

  .action-btn {
    background: transparent;
    border: 1px solid var(--color-primary);
    color: var(--color-primary);
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    flex: 1;
  }

  .action-btn:hover {
    background: var(--color-primary-transparent);
  }

  .cover-art-container {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
    max-width: 200px;
    margin: 0 auto 20px;
  }

  .cover-art {
    width: 100%;
    height: 100%;
    border-radius: 8px;
    overflow: hidden;
    background: #f0f0f0;
    position: relative;
  }

  .cover-art-size {
    position: absolute;
    left: 50%;
    bottom: 8px;
    z-index: 2;
    transform: translateX(-50%);
    padding: 2px 6px;
    border-radius: 4px;
    background: white;
    color: var(--color-primary);
    font-size: 11px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s;
  }

  .cover-art:hover .cover-art-size,
  .cover-art.editing .cover-art-size {
    opacity: 1;
  }

  .cover-art-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.2s;
    border-radius: 8px;
  }

  .cover-art:hover .cover-art-overlay,
  .cover-art.editing .cover-art-overlay {
    opacity: 1;
  }

  .cover-art-actions {
    display: flex;
    gap: 8px;
    justify-content: center;
    align-items: center;
  }

  .cover-art-actions .icon-btn {
    background: white;
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
    position: relative;
  }

  .cover-art-actions .icon-btn:hover {
    background: var(--color-primary);
    color: white;
  }

  .cover-art-actions .icon-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .cover-art-actions .icon-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .cover-art-actions .icon-btn svg {
    width: 14px;
    height: 16px;
    display: block;
  }

  .cover-url-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: -8px 0 16px;
  }

  .cover-url-field label {
    font-size: 12px;
    font-weight: 500;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .cover-url-input-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
  }

  .cover-url-input-wrapper input {
    width: 100%;
    padding: 8px 76px 8px 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
    background: white;
    color: #333;
    box-sizing: border-box;
  }

  .cover-url-actions {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px;
    background: white;
    border-radius: 4px;
  }

  .cover-url-actions .icon-btn {
    width: 28px;
    height: 28px;
    padding: 4px;
    background: none;
    border: none;
    border-radius: 4px;
    color: #666;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .cover-url-actions .icon-btn:hover {
    background: rgba(0, 0, 0, 0.1);
    color: var(--color-primary);
  }

  .cover-url-actions .icon-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .cover-url-actions .icon-btn svg {
    width: 14px;
    height: 16px;
    display: block;
  }

  :global(.hold-button.icon.cover-url-icon) {
    width: 28px;
    height: 28px;
    padding: 4px;
    color: #666;
  }

  :global(.hold-button.icon.cover-url-icon:hover:not(.disabled)) {
    background: rgba(0, 0, 0, 0.1);
    color: var(--color-primary);
  }

  .uploading-indicator {
    color: white;
    font-size: 14px;
    background: rgba(0, 0, 0, 0.7);
    padding: 8px 16px;
    border-radius: 4px;
  }

  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    gap: 8px;
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
    flex: 1;
    margin-bottom: 0; /* Override the previous margin */
  }

  /* Adjust padding for 3 icons */
  .field.editing input,
  .field.editing textarea {
    padding-right: 100px; /* Slightly larger for 3 icons */
  }

  /* Make space for the delete button on the left */
  .input-wrapper input,
  .input-wrapper textarea {
    width: 100%;
    padding-left: 10px; /* Normal padding */
  }

  .cover-art-expand {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 15;
  }

  .cover-art-expand .icon-btn {
    background: white;
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
    box-shadow: none;
    backdrop-filter: none;
  }

  .cover-art-expand .icon-btn:hover {
    background: var(--color-primary);
    color: white;
  }

  .cover-art-expand .icon-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  .cover-art-expand .icon-btn svg {
    width: 14px;
    height: 16px;
    display: block;
  }

  /* Full image modal - updated */
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
    max-height: calc(85vh - 32px);
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
  }

  .full-image-dimensions {
    margin: 8px 0 0;
    color: var(--color-primary);
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    text-align: center;
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
    background: rgba(0, 0, 0, 0.1);
    color: var(--color-primary);
    border-color: rgba(255, 255, 255, 0.4);
    transform: scale(1.05);
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

  /* Lyrics Modal */
  .lyrics-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    animation: fadeIn 0.2s ease;
  }

  .lyrics-modal {
    background: white;
    border-radius: 8px;
    width: 90%;
    max-width: 700px;
    height: 70vh;
    max-height: 600px;
    display: flex;
    flex-direction: column;
    animation: scaleIn 0.2s ease;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  }

  .lyrics-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid #eee;
  }

  .lyrics-modal-header h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: #333;
  }

  .lyrics-modal-content {
    padding: 20px;
    overflow-y: hidden;
    flex: 1;
    display: flex;
    min-height: 0; /* Critical for flex children to respect container height */
  }

  .lyrics-textarea {
    width: 100%;
    height: 100%; /* Take full height of parent */
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
    font-family: inherit;
    resize: vertical;
    box-sizing: border-box;
    overflow-y: auto;
    max-height: 100%; /* Ensure it doesn't exceed parent */
  }

  .lyrics-textarea:focus {
    outline: none;
    border-color: var(--color-primary);
  }

  .lyrics-modal-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 20px;
    border-top: 1px solid #eee;
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

  .save-actions {
    display: flex;
    gap: 4px;
  }

  .save-btn {
    background: transparent;
    border: 1px solid var(--color-primary);
    color: var(--color-primary);
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .save-btn:hover {
    background: var(--color-primary-transparent);
    color: var(--color-primary);
  }

  .save-btn svg {
    width: 14px;
    height: 16px;
  }

  .batch-actions {
    margin-top: 24px;
    display: flex;
    justify-content: center;
  }

  .batch-apply-btn {
    background: transparent;
    border: 1px solid var(--color-primary);
    color: var(--color-primary);
    padding: 10px 20px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: all 0.2s;
    width: 100%;
  }

  .batch-apply-btn:hover {
    background: var(--color-primary-transparent);
    transform: none;
    box-shadow: none;
  }

  .batch-apply-btn svg {
    stroke: var(--color-primary);
    width: 16px;
    height: 16px;
  }

  .operation-controls {
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
    padding: 8px 12px;
    background: rgba(0, 0, 0, 0.02);
    border-radius: 4px;
    border-left: 2px solid var(--color-primary);
    flex-wrap: wrap;
  }

  .readonly-banner {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 16px;
    padding: 8px 12px;
    border-radius: 4px;
    border-left: 2px solid #d9a406;
    background: rgba(217, 164, 6, 0.12);
    color: #8a6d3b;
    font-size: 12px;
    line-height: 1.45;
  }

  .readonly-badge {
    flex-shrink: 0;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(217, 164, 6, 0.2);
  }

  .metadata-editor.readonly .input-wrapper input,
  .metadata-editor.readonly .input-wrapper textarea {
    cursor: default;
    color: #777;
    background: rgba(0, 0, 0, 0.02);
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #666;
    cursor: pointer;
    white-space: nowrap;
  }

  .checkbox-label input[type="checkbox"] {
    margin: 0;
    cursor: pointer;
    accent-color: var(--color-primary-dark);
    width: 14px;
    height: 14px;
  }

  /* Dirty field indicator styles */
  .field.dirty label {
    position: relative;
  }

  .field.dirty label::after {
    content: "●";
    color: var(--color-primary);
    font-size: 12px;
    margin-left: 6px;
    display: inline-block;
    animation: pulse 1.5s ease-in-out;
  }

  /* Dark mode adjustments */
  :global(body.dark) .filename-badge {
    background: rgba(255, 255, 255, 0.1);
    color: #ccc;
  }

  :global(body.dark) .readonly-banner {
    background: rgba(217, 164, 6, 0.16);
    color: #e0c168;
  }

  :global(body.dark) .readonly-badge {
    background: rgba(217, 164, 6, 0.25);
  }

  :global(body.dark) .metadata-editor.readonly .input-wrapper input,
  :global(body.dark) .metadata-editor.readonly .input-wrapper textarea {
    color: #aaa;
    background: rgba(255, 255, 255, 0.04);
  }

  :global(body.dark) .field label {
    color: #aaa;
  }

  :global(body.dark) .input-wrapper input,
  :global(body.dark) .input-wrapper textarea,
  :global(body.dark) .field.custom input {
    background: #3d3d3d;
    border-color: #555;
    color: #e0e0e0;
  }

  :global(body.dark) .field-actions {
    background: #3d3d3d;
  }

  :global(body.dark) .icon-btn {
    color: #aaa;
  }

  :global(body.dark) .icon-btn:hover {
    background: rgba(255, 255, 255, 0.1);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .other-section {
    border-color: #444;
  }

  :global(body.dark) .collapse-toggle {
    color: var(--color-primary-dark);
  }

  :global(body.dark) .add-field-btn {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .add-field-btn:hover {
    background: var(--color-primary-transparent-dark);
  }

  :global(body.dark) .action-btn {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .action-btn:hover {
    background: var(--color-primary-transparent-dark);
  }

  :global(body.dark) .cover-art-size {
    background: #3d3d3d;
    color: var(--color-primary-dark);
  }

  :global(body.dark) .cover-art-actions .icon-btn {
    background: #3d3d3d;
    color: #e0e0e0;
  }

  :global(body.dark) .cover-art-actions .icon-btn:hover {
    background: var(--color-primary-dark);
    color: white;
  }

  :global(body.dark) .cover-art-expand .icon-btn {
    background: #3d3d3d;
    color: #e0e0e0;
  }

  :global(body.dark) .cover-art-expand .icon-btn:hover {
    background: var(--color-primary-dark);
    color: white;
  }

  :global(body.dark) .cover-url-field label {
    color: #aaa;
  }

  :global(body.dark) .cover-url-input-wrapper input {
    background: #3d3d3d;
    border-color: #555;
    color: #e0e0e0;
  }

  :global(body.dark) .cover-url-actions {
    background: #3d3d3d;
  }

  :global(body.dark) .cover-url-actions .icon-btn {
    color: #aaa;
  }

  :global(body.dark) .cover-url-actions .icon-btn:hover {
    background: rgba(255, 255, 255, 0.1);
    color: var(--color-primary-dark);
  }

  :global(body.dark .hold-button.icon.cover-url-icon) {
    color: #aaa;
  }

  :global(body.dark .hold-button.icon.cover-url-icon:hover:not(.disabled)) {
    background: rgba(255, 255, 255, 0.1);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .lyrics-modal {
    background: #2d2d2d;
    border-color: #444;
  }

  :global(body.dark) .lyrics-modal-header {
    border-color: #444;
  }

  :global(body.dark) .lyrics-modal-header h3 {
    color: #e0e0e0;
  }

  :global(body.dark) .full-image-dimensions {
    color: var(--color-primary-dark);
  }

  :global(body.dark) .modal-close-btn {
    border-color: rgba(255, 255, 255, 0.15);
  }

  :global(body.dark) .modal-close-btn:hover {
    background: rgba(0, 0, 0, 0.1);
    color: var(--color-primary-dark);
    border-color: rgba(255, 255, 255, 0.4);
    transform: scale(1.05);
  }

  :global(body.dark) .lyrics-textarea {
    background: #3d3d3d;
    border-color: #555;
    color: #e0e0e0;
  }

  :global(body.dark) .lyrics-modal-footer {
    border-color: #444;
  }

  :global(body.dark) .cancel-btn {
    border-color: #555;
    color: #aaa;
  }

  :global(body.dark) .cancel-btn:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  :global(body.dark) .save-btn {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .save-btn:hover {
    background: var(--color-primary-transparent-dark);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .batch-apply-btn {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
  }

  :global(body.dark) .batch-apply-btn:hover {
    background: var(--color-primary-transparent-dark);
  }

  :global(body.dark) .batch-apply-btn svg {
    stroke: var(--color-primary-dark);
  }

  :global(body.dark) .operation-controls {
    background: rgba(255, 255, 255, 0.05);
    border-left-color: var(--color-primary-dark);
  }

  :global(body.dark) .checkbox-label {
    color: #aaa;
  }
</style>
