// src/utils/sort.utils.js

import { writable } from 'svelte/store';

export const sortConfig = writable({
    by: 'name',        // 'name', 'created', 'modified'
    direction: 'asc'    // 'asc' or 'desc'
});

// Helper function to sort items
export function sortItems(items, sortBy, direction) {
    if (!items || items.length === 0) return items;
    
    // First, separate directories and files
    const directories = items.filter(item => item.type === 'directory');
    const files = items.filter(item => item.type === 'file');

    // Sort function
    const sorter = (a, b) => {
        let aVal, bVal;
        
        switch (sortBy) {
            case 'created':
                aVal = a.created || 0;
                bVal = b.created || 0;
                break;
            case 'modified':
                aVal = a.modified || 0;
                bVal = b.modified || 0;
                break;
            case 'name':
            default:
                aVal = a.name.toLowerCase();
                bVal = b.name.toLowerCase();
                break;
        }

        // For timestamps, ensure we're comparing numbers
        if (sortBy === 'created' || sortBy === 'modified') {
            aVal = Number(aVal);
            bVal = Number(bVal);
        }

        // Compare based on direction
        if (direction === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    };

    // Sort directories and files separately, then combine
    return [
        ...directories.sort(sorter),
        ...files.sort(sorter)
    ];
}