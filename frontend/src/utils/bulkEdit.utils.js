// src/utils/bulkEdit.utils.js

export const BULK_FILE_LIMIT = 500;

/**
 * Tree node fields the bulk editor reads; the real tree adds more.
 * @typedef {Object} BulkTreeNode
 * @property {string} name
 * @property {string} path
 * @property {string} type
 * @property {string} [file_type]
 * @property {BulkTreeNode[]} [children]
 */

/**
 * @typedef {Object} BulkAudioFile
 * @property {string} path
 * @property {string} name
 * @property {string} relativePath
 */

/**
 * @typedef {Object} CommonValue
 * @property {string} value - shared value, or "" when the files differ
 * @property {boolean} mixed - true when the files hold different values
 */

/**
 * @typedef {{ action: "set", value: string } | { action: "delete" }} FieldEdit
 */

/**
 * Collect the audio files of a folder, optionally walking subfolders.
 *
 * @param {BulkTreeNode | null | undefined} folderNode
 * @param {boolean} recursive
 * @param {number} [limit]
 * @returns {BulkAudioFile[]}
 */
export function collectAudioFiles(
  folderNode,
  recursive,
  limit = BULK_FILE_LIMIT,
) {
  /** @type {BulkAudioFile[]} */
  const result = [];
  if (!folderNode || folderNode.type !== "directory") return result;

  /**
   * @param {BulkTreeNode} node
   * @param {string} prefix
   */
  function walk(node, prefix) {
    for (const child of node.children ?? []) {
      if (result.length >= limit) return;
      const relativePath = prefix ? `${prefix}/${child.name}` : child.name;
      if (child.type === "file" && child.file_type === "audio") {
        result.push({ path: child.path, name: child.name, relativePath });
      } else if (recursive && child.type === "directory") {
        walk(child, relativePath);
      }
    }
  }

  walk(folderNode, "");
  return result;
}

/**
 * Work out, per field, whether every file shares one value.
 *
 * Missing values count as "", so a field set on some files and empty on
 * others is reported as mixed.
 *
 * @param {Record<string, unknown>[]} metadataList
 * @param {string[]} fields
 * @returns {Record<string, CommonValue>}
 */
export function computeCommonValues(metadataList, fields) {
  /** @type {Record<string, CommonValue>} */
  const result = {};
  for (const field of fields) {
    const values = new Set(
      metadataList.map((meta) => {
        const value = meta?.[field];
        return typeof value === "string" ? value : "";
      }),
    );
    if (values.size === 1) {
      result[field] = { value: [...values][0], mixed: false };
    } else {
      result[field] = { value: "", mixed: values.size > 1 };
    }
  }
  return result;
}

/**
 * @param {string} value
 * @returns {boolean}
 */
export function isValidDiskNumber(value) {
  return /^\d+(\/\d+)?$/.test(value.trim());
}

/**
 * Build the body for POST /api/metadata/batch from the touched fields.
 *
 * @param {string[]} paths
 * @param {Record<string, FieldEdit>} edits
 * @returns {{ paths: string[], set: Record<string, string>, delete: string[] }}
 */
export function buildBatchBody(paths, edits) {
  /** @type {Record<string, string>} */
  const set = {};
  /** @type {string[]} */
  const deletions = [];
  for (const [field, edit] of Object.entries(edits)) {
    if (edit.action === "delete") deletions.push(field);
    else set[field] = edit.value;
  }
  return { paths: [...paths], set, delete: deletions };
}
