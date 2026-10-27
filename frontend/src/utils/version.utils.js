// src/utils/version.utils.js

// Shared /api/version lookup. The app needs the same payload for the
// version/update check and for the upload limit, so cache the in-flight
// promise: a page load must only issue one request.

import { getAuthHeaders } from "../stores/auth.store.js";
import { readApiError, readJsonResponse } from "./api.utils.js";

const VERSION_FALLBACK = "Could not read the version information";

/** @type {Promise<any> | null} */
let versionRequest = null;

/**
 * Fetch `/api/version`, reusing the cached request/result.
 *
 * A failed request clears the cache so a later call can retry instead of
 * reusing a rejected promise.
 */
export function fetchVersionInfo() {
  if (!versionRequest) {
    versionRequest = (async () => {
      const response = await fetch("/api/version", {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, VERSION_FALLBACK));
      }
      return readJsonResponse(response, VERSION_FALLBACK);
    })().catch((error) => {
      versionRequest = null;
      throw error;
    });
  }

  return versionRequest;
}
