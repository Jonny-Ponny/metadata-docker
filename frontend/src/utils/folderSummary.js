// src/utils/folderSummary.js

/**
 * Recursively count folders, files, and calculate total size
 * @param {Object} folderNode - The folder node from treeData
 * @returns {Object} Summary object with counts and total size
 */
export function getFolderSummary(folderNode) {
    // Safety check - make sure we have a valid folder
    if (!folderNode || folderNode.type !== 'directory') {
        return null;
    }

    let totalSize = 0;        // Total size in bytes
    let folderCount = 0;      // Number of subfolders
    let fileCount = 0;        // Number of files
    let formatCounts = {};    // Object to track file formats (e.g., {mp3: 5, flac: 3})

    // Recursive function to traverse folder tree
    function traverse(node) {
        if (node.type === 'directory') {
            // Found a subfolder
            folderCount++;
            // Check its children
            if (node.children) {
                node.children.forEach(child => traverse(child));
            }
        } else if (node.type === 'file') {
            // Found a file
            fileCount++;
            totalSize += node.size || 0;  // Add file size

            // Extract and count file extension
            const ext = getFileExtension(node.name);
            if (ext) {
                formatCounts[ext] = (formatCounts[ext] || 0) + 1;
            }
        }
    }

    // Start traversing from the folder's children
    if (folderNode.children) {
        folderNode.children.forEach(child => traverse(child));
    }

    // Return the summary
    return {
        folderCount,      // Number of subfolders
        fileCount,        // Number of files
        totalSize,        // Total size in bytes
        formatCounts,     // Object with format counts
        totalItems: folderCount + fileCount  // Total items count
    };
}

/**
 * Extract file extension from filename
 * @param {string} filename - The filename
 * @returns {string} Uppercase extension (e.g., 'MP3', 'JPG')
 */
function getFileExtension(filename) {
    const lastDot = filename.lastIndexOf('.');
    if (lastDot === -1) return 'unknown';
    return filename.substring(lastDot + 1).toUpperCase();
}

/**
 * Convert bytes to human-readable format
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size (e.g., '1.2 GB', '45 MB')
 */
export function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}