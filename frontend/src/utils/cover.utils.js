// src/utils/cover.utils.js
import { readApiError } from "./api.utils.js";

/**
 * Set cover art from a remote image URL.
 *
 * The backend downloads the image through its SSRF guard, so the browser
 * never contacts the remote host.
 *
 * @param {string} path File path, or folder path when `toFolder` is set.
 * @param {string} url Public http(s) image URL.
 * @param {{ toFolder?: boolean, recursive?: boolean }} [options]
 * @returns {Promise<any>}
 */
export async function setCoverFromUrl(path, url, options = {}) {
  const { toFolder = false, recursive = false } = options;
  const endpoint = !toFolder
    ? "url"
    : recursive
      ? "url/folder"
      : "url/folder/current";

  const response = await fetch(`/api/metadata/picture/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, url }),
  });

  if (!response.ok) {
    throw new Error(
      await readApiError(response, "Failed to set cover art from URL"),
    );
  }

  return response.json();
}
