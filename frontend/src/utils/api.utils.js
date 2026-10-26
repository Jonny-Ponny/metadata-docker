// src/utils/api.utils.js

const MAX_PLAIN_TEXT_LENGTH = 200;

function withStatus(fallback, status) {
  return status ? `${fallback} (HTTP ${status})` : fallback;
}

/**
 * Turn an error response body into a readable message.
 *
 * The backend normally answers with JSON such as `{"error": "Invalid new name"}`.
 * Proxies and crashes can still return HTML or plain text, so markup and
 * oversized bodies are ignored in favour of the caller's fallback.
 */
export function messageFromBody(body) {
  const text = (body || "").trim();
  if (!text) return "";

  if (text.startsWith("{")) {
    try {
      const data = JSON.parse(text);
      for (const key of ["error", "message"]) {
        const value = data?.[key];
        if (typeof value === "string" && value.trim()) return value.trim();
        if (value && typeof value === "object") {
          if (typeof value.message === "string" && value.message.trim()) {
            return value.message.trim();
          }
        }
      }
    } catch {
      // Malformed JSON: fall through to the fallback message.
    }
    return "";
  }

  if (text.startsWith("<")) return "";
  if (text.length > MAX_PLAIN_TEXT_LENGTH) return "";
  return text;
}

/**
 * Build a readable message from a raw response body and status code.
 *
 * XHR responses do not produce a `Response` object, so uploads need the same
 * parsing that `readApiError` applies to fetch responses.
 */
export function formatApiErrorMessage(
  body,
  fallback = "Request failed",
  status,
) {
  return messageFromBody(body) || withStatus(fallback, status);
}

/**
 * Read an error message from a failed fetch response.
 *
 * The body is consumed exactly once, so call this only when `response.ok` is
 * false. Returns the backend's `error`/`message` when present, a short plain
 * text body otherwise, and always appends the HTTP status to the fallback.
 */
export async function readApiError(response, fallback = "Request failed") {
  const status = response?.status;
  let body;

  try {
    body = await response.text();
  } catch {
    return withStatus(fallback, status);
  }

  return messageFromBody(body) || withStatus(fallback, status);
}

/**
 * Parse a JSON response body, converting malformed JSON into a readable error.
 */
export async function readJsonResponse(
  response,
  fallback = "Unexpected server response",
) {
  const text = await response.text();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(withStatus(fallback, response?.status));
  }
}
