// src/utils/settings.utils.js

import { writable } from "svelte/store";
import { getAuthHeaders } from "../stores/auth.store";

// Allowed variables for renaming schemes
export const ALLOWED_VARIABLES = {
    'TITLE': 'title',
    'ALBUM': 'album',
    'ARTIST': 'artist',
    'ALBUMARTIST': 'albumArtist',
    'YYYY': 'year',                  // Will extract just the year from date
    'TRACK': 'track',
    'DISK': 'disk',                  // Disk number
    'RELEASETYPE': 'releaseType',    // Release type (album, ep, etc.)
};

// Default settings
const defaultSettings = {
    allowDeleteKey: true,
    folderScheme: "[[YYYY]] - [ALBUMARTIST] - [ALBUM]",          // Scheme for folders
    fileScheme: "[ALBUMARTIST] - [ALBUM] - [TRACK] - [TITLE]",   // Scheme for files
    replaceSpacesInFolders: false,                               // Setting for folders
    replaceSpacesInFiles: false,                                 // Setting for files
    enablePlayer: true                                           // Player enabled by default
};

// Load settings from localStorage
function loadSettings() {
    try {
        const saved = localStorage.getItem("appSettings");
        if (saved) {
            const parsed = JSON.parse(saved);
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