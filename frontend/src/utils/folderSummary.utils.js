// src/utils/folderSummary.utils.js

/**
 * Tree node fields the summary reads; the real tree adds more.
 * @typedef {Object} TreeEntry
 * @property {string} name
 * @property {string} type
 * @property {number} [size]
 * @property {TreeEntry[] | null} [children]
 * @property {number} [folder_count] direct child folders, from /api/files/dir
 * @property {number} [file_count] direct child files
 * @property {number} [file_size] size of the direct child files only
 */

/**
 * @typedef {Object} FolderSummary
 * @property {number} folderCount
 * @property {number} fileCount
 * @property {number} totalSize
 * @property {Record<string, number>} formatCounts
 * @property {number} totalItems
 */

/**
 * Recursively count folders, files, and calculate total size.
 *
 * Prefers the direct-child counts the backend returns with a folder listing
 * (`folder_count`, `file_count`, `file_size`), so a tooltip does not walk the
 * subtree. Nodes without those fields fall back to the recursive walk.
 * @param {TreeEntry} [folderNode] - The folder node from treeData
 * @returns {FolderSummary | null} Summary object with counts and total size
 */
export function getFolderSummary(folderNode) {
  // Safety check - make sure we have a valid folder
  if (!folderNode || folderNode.type !== "directory") {
    return null;
  }

  // A lazy folder listing knows its direct-child counts already.
  if (typeof folderNode.folder_count === "number") {
    const folderCount = folderNode.folder_count;
    const fileCount = folderNode.file_count || 0;
    const totalSize = folderNode.file_size || 0;
    return {
      folderCount,
      fileCount,
      totalSize,
      formatCounts: countFormats(folderNode.children),
      totalItems: folderCount + fileCount,
    };
  }

  let totalSize = 0; // Total size in bytes
  let folderCount = 0; // Number of subfolders
  let fileCount = 0; // Number of files
  /** @type {Record<string, number>} */
  let formatCounts = {}; // Object to track file formats (e.g., {mp3: 5, flac: 3})

  // Recursive function to traverse folder tree
  /**
   * @param {TreeEntry} node
   */
  function traverse(node) {
    if (node.type === "directory") {
      // Found a subfolder
      folderCount++;
      // Check its children
      if (node.children) {
        node.children.forEach((child) => traverse(child));
      }
    } else if (node.type === "file") {
      // Found a file
      fileCount++;
      totalSize += node.size || 0; // Add file size

      // Extract and count file extension
      const ext = getFileExtension(node.name);
      if (ext) {
        formatCounts[ext] = (formatCounts[ext] || 0) + 1;
      }
    }
  }

  // Start traversing from the folder's children
  if (folderNode.children) {
    folderNode.children.forEach((child) => traverse(child));
  }

  // Return the summary
  return {
    folderCount, // Number of subfolders
    fileCount, // Number of files
    totalSize, // Total size in bytes
    formatCounts, // Object with format counts
    totalItems: folderCount + fileCount, // Total items count
  };
}

/**
 * Count file extensions in one level of children.
 * @param {TreeEntry[] | null | undefined} children
 * @returns {Record<string, number>}
 */
function countFormats(children) {
  /** @type {Record<string, number>} */
  const formatCounts = {};
  for (const child of children || []) {
    if (child.type !== "file") continue;
    const ext = getFileExtension(child.name);
    if (ext) formatCounts[ext] = (formatCounts[ext] || 0) + 1;
  }
  return formatCounts;
}

/** Format lines kept in a tooltip before the rest are collapsed. */
export const MAX_FORMAT_LINES = 5;

/**
 * Tooltip text for a folder row.
 *
 * Uses the deep totals from `/api/files/summary` when they are available and
 * falls back to the direct-child counts from the folder listing otherwise.
 * `loading` prepends a "Calculating…" line so the tooltip does not appear to
 * settle on a number and then change.
 *
 * At most `MAX_FORMAT_LINES` format lines are shown; the rest are collapsed
 * into a "+N more" line so a folder with many extensions cannot grow the
 * tooltip past the viewport.
 *
 * @param {{ children?: TreeEntry[] | null, folder_count?: number, file_count?: number, file_size?: number, format_counts?: Record<string, number> }} folderNode
 * @param {{ loading?: boolean }} [options]
 * @returns {string}
 */
export function formatFolderSummary(folderNode, { loading = false } = {}) {
  const summary = getFolderSummary(
    /** @type {TreeEntry} */ ({
      name: "",
      children: folderNode?.children ?? [],
      ...folderNode,
      type: "directory",
    }),
  );

  if (!summary || summary.totalItems === 0) {
    return loading ? "Calculating…" : "Empty folder";
  }

  const lines = [];
  if (loading) lines.push("Calculating…");

  lines.push(formatFileSize(summary.totalSize));
  if (summary.folderCount > 0) {
    lines.push(`folders x${summary.folderCount}`);
  }

  const counts = folderNode.format_counts ?? summary.formatCounts;
  const formats = Object.entries(counts).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  for (const [format, count] of formats.slice(0, MAX_FORMAT_LINES)) {
    lines.push(`${format.toLowerCase()} x${count}`);
  }
  if (formats.length > MAX_FORMAT_LINES) {
    lines.push(`+${formats.length - MAX_FORMAT_LINES} more formats`);
  }
  return lines.join("\n");
}

/**
 * Extract file extension from filename
 * @param {string} filename - The filename
 * @returns {string} Uppercase extension (e.g., 'MP3', 'JPG')
 */
function getFileExtension(filename) {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot === -1) return "unknown";
  return filename.substring(lastDot + 1).toUpperCase();
}

/**
 * Convert bytes to human-readable format
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size (e.g., '1.2 GB', '45 MB')
 */
export function formatFileSize(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}
