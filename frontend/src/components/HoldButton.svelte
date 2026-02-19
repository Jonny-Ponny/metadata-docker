<script>
    import { holdToConfirm } from "../utils/index.js";

    let {
        onConfirm = () => {},
        duration = 800,
        variant = "icon", // 'icon', 'menu', 'text'
        title = "",
        disabled = false,
        class: className = "",
        children,
    } = $props();

    let progress = $state(0);
    let isHolding = $state(false);
    let buttonRef = $state(null);

    function handleConfirm(e) {
        onConfirm(e);
    }

    function handleStart() {
        isHolding = true;
    }

    function handleCancel() {
        isHolding = false;
        progress = 0;
    }

    function handleProgress(p) {
        progress = p;
    }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
    class="hold-button {variant} {className}"
    class:holding={isHolding}
    class:disabled
    use:holdToConfirm={{
        duration,
        onConfirm: handleConfirm,
        onStart: handleStart,
        onCancel: handleCancel,
        onProgress: handleProgress,
    }}
    bind:this={buttonRef}
    {title}
    role="button"
    tabindex="0"
    aria-disabled={disabled}
>
    <!-- Progress indicator -->
    <div class="progress-indicator" style="--progress: {progress};">
        {#if variant === "icon"}
            <!-- Icon buttons - preserve original styling -->
            <span class="icon-content">
                {@render children()}
            </span>
        {:else if variant === "menu"}
            <!-- Menu items -->
            <span class="menu-text">{@render children()}</span>
            <span class="progress-fill"></span>
        {:else}
            <!-- Text buttons -->
            <span class="btn-text">{@render children()}</span>
            <span class="progress-fill"></span>
        {/if}
    </div>
</div>

<style>
    .hold-button {
        position: relative;
        cursor: pointer;
        overflow: hidden;
        user-select: none;
        -webkit-tap-highlight-color: transparent;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .hold-button.disabled {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
    }

    .hold-button.icon {
        background: none;
        border: none;
        padding: 4px;
        border-radius: 4px;
        color: #666;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.15s;
        width: auto;
        height: auto;
        line-height: 0;
        box-sizing: border-box;
        position: relative;
    }

    /* Cover art specific styling - larger */
    .hold-button.icon.cover-art-icon {
        background: white;
        padding: 8px;
        width: 32px;
        height: 32px;
    }

    /* Match the exact hover behavior of original icon-btn */
    .hold-button.icon:hover:not(.disabled) {
        background: rgba(0, 0, 0, 0.1);
        color: #fd7d05;
    }

    .hold-button.icon.cover-art-icon:hover:not(.disabled) {
        background: #fd7d05;
        color: white;
    }

    /* Make sure progress fill is visible */
    .hold-button.icon .progress-indicator {
        position: relative;
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .hold-button.icon .icon-content {
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        z-index: 2;
    }

    /* Progress fill for icons - bottom to top */
    .hold-button.icon .progress-indicator::after {
        content: "";
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        height: calc(100% * var(--progress));
        background: #fd7d05;
        opacity: 0.5; /* Increased from 0.3 to 0.5 */
        transition: height 0.1s linear;
        pointer-events: none;
        z-index: 1;
        border-radius: 3px;
    }

    /* For cover art icons, make it even more visible */
    .hold-button.icon.cover-art-icon .progress-indicator::after {
        opacity: 0.7; /* Higher opacity for cover art icons */
        background: #fd7d05;
        box-shadow: inset 0 0 0 1px rgba(253, 125, 5, 0.3); /* Add a subtle border */
    }

    /* For delete button in cover art */
    .hold-button.icon.cover-art-icon.delete-btn .progress-indicator::after {
        background: #ff4444;
        opacity: 0.7;
        box-shadow: inset 0 0 0 1px rgba(255, 68, 68, 0.3);
    }

    /* Menu item variant */
    .hold-button.menu {
        width: 100%;
        padding: 0;
        color: #ff4444;
    }

    .hold-button.menu .progress-indicator {
        position: relative;
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
    }

    .hold-button.menu .menu-text {
        position: relative;
        z-index: 2;
        padding: 8px 16px;
        width: 100%;
        text-align: left;
        font-size: 14px;
    }

    .hold-button.menu .progress-fill {
        position: absolute;
        top: 0;
        left: 0;
        width: calc(100% * var(--progress));
        height: 100%;
        background: #ff8989;
        opacity: 0.2;
        transition: width 0.1s linear;
        pointer-events: none;
        z-index: 1;
    }

    .hold-button.menu:hover:not(.disabled) {
        background-color: #f0f0f0;
    }

    /* Text button variant */
    .hold-button.text {
        background: transparent;
        border: 1px solid currentColor;
        border-radius: 4px;
        padding: 0;
        overflow: hidden;
        color: #fd7d05;
    }

    .hold-button.text .progress-indicator {
        position: relative;
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .hold-button.text .btn-text {
        position: relative;
        z-index: 2;
        padding: 8px 16px;
        width: 100%;
        text-align: center;
        font-size: 13px;
    }

    .hold-button.text .progress-fill {
        position: absolute;
        top: 0;
        left: 0;
        width: calc(100% * var(--progress));
        height: 100%;
        background: #fd7d05;
        opacity: 0.15;
        transition: width 0.1s linear;
        pointer-events: none;
        z-index: 1;
    }

    .hold-button.text:hover:not(.disabled) {
        background: rgba(253, 125, 5, 0.1);
    }

    /* Holding state visual feedback */
    .hold-button.holding {
        opacity: 0.9;
    }

    .hold-button.icon.holding {
        background: rgba(253, 125, 5, 0.1); /* Orange tint when holding */
    }

    /* Delete button styling */
    .hold-button.icon.delete-btn {
        color: #ff4444;
    }

    .hold-button.icon.delete-btn:hover:not(.disabled) {
        background: rgba(255, 68, 68, 0.1);
        color: #ff4444;
    }

    .hold-button.icon.delete-btn .progress-indicator::after {
        background: #ff4444;
    }

    /* Cover art delete button */
    .hold-button.icon.cover-art-icon.delete-btn:hover:not(.disabled) {
        background: #ff4444;
        color: white;
    }

    /* Dark mode adjustments */
    :global(body.dark) .hold-button.icon {
        color: #aaa;
    }

    :global(body.dark) .hold-button.icon:hover:not(.disabled) {
        background: rgba(255, 255, 255, 0.1);
        color: #ff9f4b;
    }

    :global(body.dark) .hold-button.icon.cover-art-icon {
        background: #3d3d3d;
        color: #e0e0e0;
    }

    :global(body.dark) .hold-button.icon.cover-art-icon:hover:not(.disabled) {
        background: #ff9f4b;
        color: white;
    }

    :global(body.dark) .hold-button.menu {
        color: #ff6b6b;
    }

    :global(body.dark) .hold-button.menu:hover:not(.disabled) {
        background-color: #3d3d3d;
    }

    :global(body.dark) .hold-button.menu .progress-fill {
        background: #ff8f8f;
        opacity: 0.3;
    }

    :global(body.dark) .hold-button.text {
        color: #ff9f4b;
    }

    :global(body.dark) .hold-button.text:hover:not(.disabled) {
        background: rgba(255, 159, 75, 0.1);
    }

    :global(body.dark) .hold-button.icon.holding {
        background: rgba(255, 159, 75, 0.2);
    }

    :global(body.dark) .hold-button.icon .progress-indicator::after {
        background: #ff9f4b;
        opacity: 0.6; /* Increased from 0.4 to 0.6 */
    }

    :global(body.dark)
        .hold-button.icon.cover-art-icon
        .progress-indicator::after {
        opacity: 0.8; /* Even higher for dark mode cover art */
        background: #ff9f4b;
        box-shadow: inset 0 0 0 1px rgba(255, 159, 75, 0.4);
    }

    :global(body.dark)
        .hold-button.icon.cover-art-icon.delete-btn
        .progress-indicator::after {
        background: #ff6b6b;
        opacity: 0.8;
        box-shadow: inset 0 0 0 1px rgba(255, 107, 107, 0.4);
    }

    :global(body.dark) .hold-button.icon.delete-btn {
        color: #ff6b6b;
    }

    :global(body.dark) .hold-button.icon.delete-btn:hover:not(.disabled) {
        background: rgba(255, 107, 107, 0.2);
    }

    :global(body.dark) .hold-button.icon.cover-art-icon.delete-btn {
        background: #3d3d3d;
        color: #ff6b6b;
    }

    :global(body.dark)
        .hold-button.icon.cover-art-icon.delete-btn:hover:not(.disabled) {
        background: #ff6b6b;
        color: white;
    }
</style>
