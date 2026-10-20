// src/utils/settings.utils.js

import { writable } from "svelte/store";
import { getAuthHeaders } from "../stores/auth.store";
import { generateFullTheme} from "./index"

// Allowed variables for renaming schemes
export const ALLOWED_VARIABLES = {
    'TITLE': 'title',
    'ALBUM': 'album',
    'ARTIST': 'artist',
    'ALBUMARTIST': 'albumArtist',
    'YYYY': 'date',                  // Will extract just the year from date
    'TRACK': 'trackNumber',
    'DISK': 'diskNumber',            // Disk number
    'RELEASETYPE': 'releaseType',    // Release type (album, ep, etc.)
};

// All field names used in the folder overview
export const OVERVIEW_FIELD_NAMES = [
    'title',
    'album',
    'artist',
    'albumArtist',
    'trackNumber',
    'diskNumber',
    'date',
    'genre',
    'unsyncedLyrics',
    'lyrics',
    'picture',
];

// Color theme defaults
export const defaultColors = {
    'color-primary': '#fd7d05',
    'color-badge-audio': '#fd7d05',
    'color-badge-image': '#6666ff',
    'color-badge-text': '#2e7d32',
};

// Default settings
const defaultSettings = {
    allowDeleteKey: true,
    folderScheme: "[[YYYY]] - [ALBUMARTIST] - [ALBUM]",          // Scheme for folders
    fileScheme: "[ALBUMARTIST] - [ALBUM] - [TRACK] - [TITLE]",   // Scheme for files
    replaceSpacesInFolders: false,                               // Setting for folders
    replaceSpacesInFiles: false,                                 // Setting for files
    enablePlayer: true,                                          // Player enabled by default
    overviewFields: [...OVERVIEW_FIELD_NAMES],                   // All fields selected by default
    recursiveOverview: false,                                    // Recursive overview flag
    ...defaultColors,                                            // Color defaults
};

// Load settings from localStorage
function loadSettings() {
    try {
        const saved = localStorage.getItem("appSettings");
        if (saved) {
            const parsed = JSON.parse(saved);
            // Migrate old overview field names to the renamed fields.
            if (Array.isArray(parsed.overviewFields)) {
                const renames = {
                    year: "date",
                    track: "trackNumber",
                    disk: "diskNumber",
                };
                parsed.overviewFields = [
                    ...new Set(
                        parsed.overviewFields.map(
                            (field) => renames[field] || field,
                        ),
                    ),
                ];
            }
            // Merge with defaults to ensure all fields exist
            return {
                ...defaultSettings,
                ...parsed
            };
        }
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
    return defaultSettings;
}

// Create writable store
export const settings = writable(loadSettings());

// Save settings to localStorage
export function saveSettings(newSettings) {
    try {
        localStorage.setItem("appSettings", JSON.stringify(newSettings));
        settings.set(newSettings);
        applyThemeFromSettings(newSettings);
    } catch (e) {
        console.error("Failed to save settings:", e);
    }
}

// Updated to accept options parameter
export async function applyRenamingScheme(scheme, path, isFolder = true, options = {}) {
    try {
        const response = await fetch("/api/apply-renaming-scheme", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                path,
                scheme,
                isFolder,
                replaceSpaces: options.replaceSpaces || false  // Pass the option to backend
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Failed to apply renaming scheme");
        }

        return result;
    } catch (error) {
        throw new Error(`Failed to apply renaming scheme: ${error.message}`);
    }
}

export function applyThemeFromSettings(settingsObj) {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    const bases = {
        'color-primary': settingsObj['color-primary'] || defaultColors['color-primary'],
        'color-badge-audio': settingsObj['color-badge-audio'] || defaultColors['color-badge-audio'],
        'color-badge-image': settingsObj['color-badge-image'] || defaultColors['color-badge-image'],
        'color-badge-text': settingsObj['color-badge-text'] || defaultColors['color-badge-text'],
    };
    const fullTheme = generateFullTheme(bases);
    for (const [key, value] of Object.entries(fullTheme)) {
        root.style.setProperty(key, value);
    }
}