<!-- src/components/EditModal.svelte -->
<script>
  let {
    show = false,
    editingText = $bindable(), // Mark as bindable for two-way binding
    onClose = () => {},
    onSave = (text) => {},
  } = $props();
  
  let textareaElement = $state(null);

  function handleClose() {
    onClose();
  }

  function handleSave() {
    onSave(editingText);
  }

  // Focus textarea when modal opens
  $effect(() => {
    if (show && textareaElement) {
      // Small delay to ensure the DOM is fully rendered
      setTimeout(() => {
        textareaElement.focus();
      }, 100);
    }
  });

  // Add event listener to prevent keyboard events from bubbling
  $effect(() => {
    if (show) {
      const handleKeyDown = (e) => {
        // Stop propagation for all keyboard events when modal is open
        e.stopPropagation();
      };

      window.addEventListener("keydown", handleKeyDown, true); // Use capture phase

      return () => {
        window.removeEventListener("keydown", handleKeyDown, true);
      };
    }
  });
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="modal-overlay" onclick={handleClose}>
    <div class="modal-content" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>Edit Unsynchronized Lyrics</h3>
        <button title="Close" class="modal-close" onclick={handleClose}>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <textarea
          bind:this={textareaElement}
          bind:value={editingText}
          placeholder="Enter lyrics here. You can include timestamps like [00:00.00] at the beginning of lines..."
          class="edit-textarea"
          rows="15"
          onkeydown={(e) => e.stopPropagation()}
        ></textarea>
        <div class="modal-info">
          <p>Each line will create a timestamp entry</p>
          <p>You can add timestamps like [00:00.00] at line beginnings</p>
          <p>Timestamps will be extracted to the left column</p>
          <p>Use empty lines for pauses between verses</p>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick={handleClose}>
          Cancel
        </button>
        <button class="btn btn-primary" onclick={handleSave}>
          Save Changes
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(3px);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    animation: fadeIn 0.2s ease-out;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .modal-content {
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    width: 100%;
    max-width: 600px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.3s ease-out;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .modal-header {
    padding: 20px 24px;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .modal-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #333;
  }

  .modal-close {
    background: none;
    border: none;
    padding: 4px;
    cursor: pointer;
    color: #666;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .modal-close:hover {
    color: #333;
    background-color: rgba(0, 0, 0, 0.05);
  }

  .modal-body {
    padding: 24px;
    flex: 1;
    overflow-y: auto;
  }

  .edit-textarea {
    width: 100%;
    max-width: 100%;
    padding: 16px;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    resize: vertical;
    min-height: 200px;
    transition: border-color 0.2s;
    margin-bottom: 16px;
    box-sizing: border-box; /* This prevents overflow */
  }

  .edit-textarea:focus {
    outline: none;
    border-color: #fd7d05;
  }

  .modal-info {
    background-color: #f8f9fa;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 13px;
    color: #666;
    margin-top: 12px;
    box-sizing: border-box;
    width: 100%;
  }

  .modal-info p {
    margin: 4px 0;
    line-height: 1.4;
  }

  .modal-footer {
    padding: 20px 24px;
    border-top: 1px solid #e0e0e0;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    flex-shrink: 0;
  }

  /* Button styles */
  .btn {
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    border: none;
  }

  .btn-primary {
    background-color: #fd7d05;
    color: white;
  }

  .btn-primary:hover {
    background-color: #ff5e00;
  }

  .btn-secondary {
    background-color: #f0f0f0;
    color: #666;
    border: 1px solid #ddd;
  }

  .btn-secondary:hover {
    background-color: #e0e0e0;
  }

  /* Dark mode */
  :global(body.dark) .modal-content {
    background: #2d2d2d;
    color: #e0e0e0;
  }

  :global(body.dark) .modal-header {
    border-bottom-color: #444;
  }

  :global(body.dark) .modal-header h3 {
    color: #e0e0e0;
  }

  :global(body.dark) .modal-close {
    color: #b0b0b0;
  }

  :global(body.dark) .modal-close:hover {
    color: #e0e0e0;
    background-color: #3d3d3d;
  }

  :global(body.dark) .edit-textarea {
    background: #1e1e1e;
    border-color: #444;
    color: #e0e0e0;
  }

  :global(body.dark) .edit-textarea:focus {
    border-color: #ff9f4b;
  }

  :global(body.dark) .modal-info {
    background: #3d3d3d;
    color: #b0b0b0;
  }

  :global(body.dark) .btn-primary {
    background-color: #ff9f4b;
    color: #1e1e1e;
  }

  :global(body.dark) .btn-primary:hover {
    background-color: #ffb06f;
  }

  :global(body.dark) .btn-secondary {
    background-color: #3d3d3d;
    color: #e0e0e0;
    border-color: #555;
  }

  :global(body.dark) .btn-secondary:hover {
    background-color: #4d4d4d;
  }
</style>