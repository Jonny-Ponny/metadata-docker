// src/utils/audioFormats.utils.js

// Keep this list in sync with backend/formats.py. The backend is the source of
// truth for which files appear in the tree; this helper is for UI filtering and
// labels where a synchronous check is needed.
export const AUDIO_FORMAT_LABELS = {
    mp3: "MP3",
    flac: "FLAC",
    ogg: "OGG",
    oga: "OGG",
    opus: "OPUS",
};

export const AUDIO_EXTENSIONS = Object.keys(AUDIO_FORMAT_LABELS).map(
    (extension) => `.${extension}`,
);

/**
 * Return a file's lower-case extension without the leading dot.
 * @param {string} filename
 * @returns {string}
 */
export function getFileExtension(filename) {
    if (!filename) return "";
    const dot = filename.lastIndexOf(".");
    return dot === -1 ? "" : filename.substring(dot + 1).toLowerCase();
}

/**
 * True when a file is audio, using the backend file type when available.
 * @param {string} filename
 * @param {string} [fileType] - backend ``file_type`` value
 * @returns {boolean}
 */
export function isAudioFile(filename, fileType) {
    if (fileType === "audio") return true;
    return AUDIO_EXTENSIONS.includes(`.${getFileExtension(filename)}`);
}

/**
 * Human-readable format label, e.g. ``OGG`` or ``OPUS``.
 * @param {string} filename
 * @returns {string}
 */
export function getAudioFormatLabel(filename) {
    const extension = getFileExtension(filename);
    return AUDIO_FORMAT_LABELS[extension] || extension.toUpperCase();
}
