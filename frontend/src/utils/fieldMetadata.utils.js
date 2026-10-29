// src/utils/fieldMetadata.utils.js

/** @type {Record<string, { label: string, description: string }>} */
export const FIELD_METADATA = {
  title: {
    label: "Title",
    description:
      "Song title. Fundamental field that identifies the specific name of an individual piece of music",
  },
  album: {
    label: "Album",
    description:
      "Album name. Field used to store the name of the collection a song belongs to",
  },
  artist: {
    label: "Artist",
    description:
      "Artist name. Identifies the specific performer(s) for a single song",
  },
  albumArtist: {
    label: "Album Artist",
    description:
      "Specific field used to identify the primary artist or group responsible for an entire album. It is separate from the standard Artist (or Track Artist) tag, which identifies the performer(s) on an individual song",
  },
  trackNumber: {
    label: "Track Number",
    description: "The track number on the album",
  },
  diskNumber: {
    label: "Disk Number",
    description: "The disc number",
  },
  date: {
    label: "Date",
    description: "Release date (YYYY or YYYY-MM-DD).",
  },
  genre: {
    label: "Genre",
    description: "The musical genre",
  },
  releaseType: {
    label: "Release Type",
    description:
      "The kind of release, for example album, EP, single or compilation",
  },
  comment: {
    label: "Comment",
    description: "Free-form notes about the track or release",
  },
  description: {
    label: "Description",
    description: "Additional free-form text describing the track or release",
  },
  composer: {
    label: "Composer",
    description: "The writer(s) or composer(s) of the track",
  },
  publisher: {
    label: "Publisher",
    description: "The label or entity that published the release",
  },
  unsyncedLyrics: {
    label: "Unsynced Lyrics",
    description: "Plain text lyrics",
  },
  lyrics: {
    label: "Synced Lyrics",
    description: "Time‑synced lyrics",
  },
  picture: {
    label: "Cover Art",
    description: "Embedded album cover image",
  },
};

// Helper to get label for a field key
/**
 * @param {string} key
 * @returns {string}
 */
export function getFieldLabel(key) {
  return FIELD_METADATA[key]?.label || key;
}

// Helper to get description for a field key
/**
 * @param {string} key
 * @returns {string}
 */
export function getFieldDescription(key) {
  return FIELD_METADATA[key]?.description || "";
}
