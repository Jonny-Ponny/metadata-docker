import { writable } from 'svelte/store';

export function createHoldToConfirm(node, options = {}) {
    const {
        duration = 800, // Hold duration in ms
        onConfirm = () => {},
        onStart = () => {},
        onCancel = () => {},
        onProgress = () => {}
    } = options;

    let timeoutId;
    let startTime;
    let progressInterval;
    let isHolding = false;
    
    // Progress store for visual feedback
    const progress = writable(0);

    function startHold(e) {
        e.preventDefault();
        if (isHolding) return;
        
        isHolding = true;
        startTime = Date.now();
        onStart(e);
        
        // Update progress periodically
        progressInterval = setInterval(() => {
            const elapsed = Date.now() - startTime;
            const currentProgress = Math.min(elapsed / duration, 1);
            progress.set(currentProgress);
            onProgress(currentProgress);
            
            if (currentProgress >= 1) {
                completeHold(e);
            }
        }, 16); // ~60fps
        
        // Set timeout for completion
        timeoutId = setTimeout(() => {
            completeHold(e);
        }, duration);
    }

    function completeHold(e) {
        if (!isHolding) return;
        
        cleanup();
        progress.set(1);
        onConfirm(e);
    }

    function cancelHold(e) {
        if (!isHolding) return;
        
        cleanup();
        progress.set(0);
        onCancel(e);
    }

    function cleanup() {
        isHolding = false;
        clearTimeout(timeoutId);
        clearInterval(progressInterval);
    }

    // Event listeners
    node.addEventListener('mousedown', startHold);
    node.addEventListener('mouseup', cancelHold);
    node.addEventListener('mouseleave', cancelHold);
    node.addEventListener('touchstart', startHold);
    node.addEventListener('touchend', cancelHold);
    node.addEventListener('touchcancel', cancelHold);

    return {
        destroy() {
            cleanup();
            node.removeEventListener('mousedown', startHold);
            node.removeEventListener('mouseup', cancelHold);
            node.removeEventListener('mouseleave', cancelHold);
            node.removeEventListener('touchstart', startHold);
            node.removeEventListener('touchend', cancelHold);
            node.removeEventListener('touchcancel', cancelHold);
        },
        
        // Expose progress store
        progress
    };
}

// Svelte action version
export function holdToConfirm(node, options) {
    const holdInstance = createHoldToConfirm(node, options);
    
    return {
        destroy: holdInstance.destroy,
        
        update(newOptions) {
            holdInstance.destroy();
            Object.assign(holdInstance, createHoldToConfirm(node, newOptions));
        }
    };
}