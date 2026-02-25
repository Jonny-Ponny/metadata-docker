import { writable } from "svelte/store";
import { getAuthHeaders } from "../stores/auth.store";

// Allowed variables for renaming schemes
export const ALLOWED_VARIABLES = {
    'TITLE': 'title',
    'ALBUM': 'album',
    'ARTIST': 'artist',
    'ALBUMARTIST': 'albumArtist',
    'YYYY': 'year',  // Will extract just the year from date
    'TRACK': 'track',
};

// Default settings
const defaultSettings = {
    allowDeleteKey: true,
    folderScheme: "[[YYYY]]_[ARTIST]_[ALBUM]",  // Scheme for folders
    fileScheme: "[TRACK]_[TITLE]"               // Scheme for files
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

export async function applyRenamingScheme(scheme, path, isFolder = true) {
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
                isFolder
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