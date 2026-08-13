// src/utils/fieldMetadata.utils.js

export const FIELD_METADATA = {
  title: {
    label: 'Title',
    description: 'Song title. Fundamental field that identifies the specific name of an individual piece of music',
  },
  album: {
    label: 'Album',
    description: 'Album name. Field used to store the name of the collection a song belongs to',
  },
  artist: {
    label: 'Artist',
    description: 'Artist name. Identifies the specific performer(s) for a single song',
  },
  albumArtist: {
    label: 'Album Artist',
    description: 'Specific field used to identify the primary artist or group responsible for an entire album. It is separate from the standard Artist (or Track Artist) tag, which identifies the performer(s) on an individual song',
  },
  track: {
    label: 'Track',
    description: 'The track number on the album',
  },
  disk: {
    label: 'Disk',
    description: 'The disc number',
  },
  year: {
    label: 'Year',
    description: 'The release date',
  },
  genre: {
    label: 'Genre',
    description: 'The musical genre',
  },
  unsyncedLyrics: {
    label: 'Unsynced Lyrics',
    description: 'Plain text lyrics',
  },
  lyrics: {
    label: 'Synced Lyrics',
    description: 'Time‑synced lyrics',
  },
  picture: {
    label: 'Cover Art',
    description: 'Embedded album cover image',
  },
};

// Helper to get label for a field key
export function getFieldLabel(key) {
  return FIELD_METADATA[key]?.label || key;
}

// Helper to get description for a field key
export function getFieldDescription(key) {
  return FIELD_METADATA[key]?.description || '';
}