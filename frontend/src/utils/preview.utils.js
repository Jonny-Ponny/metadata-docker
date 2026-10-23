// src/utils/preview.utils.js
import { getAuthHeaders } from "../stores/auth.store.js";

const MAX_CACHED_PREVIEWS = 40;
const resolvedCache = new Map();
const pendingCache = new Map();

export function isRemoteImageUrl(value) {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

function trimCache() {
  while (resolvedCache.size > MAX_CACHED_PREVIEWS) {
    const [key, objectUrl] = resolvedCache.entries().next().value;
    resolvedCache.delete(key);
    URL.revokeObjectURL(objectUrl);
  }
}

/**
 * Resolve a remote image to a local blob URL through the authenticated backend
 * preview proxy. Data/blob URLs are returned unchanged.
 *
 * Previews are cached so the same cover is only fetched once per session.
 */
export function loadPreviewImage(url) {
  if (!isRemoteImageUrl(url)) {
    return Promise.resolve(url);
  }

  const resolved = resolvedCache.get(url);
  if (resolved) {
    // Refresh insertion order so frequently used previews survive eviction.
    resolvedCache.delete(url);
    resolvedCache.set(url, resolved);
    return Promise.resolve(resolved);
  }

  const pending = pendingCache.get(url);
  if (pending) {
    return pending;
  }

  const request = fetch(
    `/api/metadata/picture/preview?url=${encodeURIComponent(url)}`,
    { headers: getAuthHeaders() },
  )
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Cover preview failed (${response.status})`);
      }

      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) {
        throw new Error("Cover preview was not an image");
      }

      const objectUrl = URL.createObjectURL(blob);
      pendingCache.delete(url);
      resolvedCache.set(url, objectUrl);
      trimCache();
      return objectUrl;
    })
    .catch((error) => {
      pendingCache.delete(url);
      throw error;
    });

  pendingCache.set(url, request);
  return request;
}
