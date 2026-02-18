<!-- src/components/SortButton.svelte -->

<script>
    import { sortConfig } from "../utils/index.js";

    let isOpen = $state(false);
    let buttonRef = $state(null);

    const sortOptions = [
        { value: "name", label: "Name" },
        { value: "created", label: "Created" },
        { value: "modified", label: "Modified" },
    ];

    function toggleMenu() {
        isOpen = !isOpen;
    }

    function setSort(option) {
        $sortConfig = {
            ...$sortConfig,
            by: option,
        };
        isOpen = false;
    }

    function toggleDirection() {
        $sortConfig = {
            ...$sortConfig,
            direction: $sortConfig.direction === "asc" ? "desc" : "asc",
        };
    }

    // Close menu when clicking outside
    function handleClickOutside(e) {
        if (buttonRef && !buttonRef.contains(e.target)) {
            isOpen = false;
        }
    }

    $effect(() => {
        if (isOpen) {
            document.addEventListener("click", handleClickOutside);
            return () =>
                document.removeEventListener("click", handleClickOutside);
        }
    });
</script>

<div class="sort-container" bind:this={buttonRef}>
    <button class="sort-btn" onclick={toggleMenu} title="Sort items">
        <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
        >
            <path d="M3 6h18M6 12h12M10 18h4" />
        </svg>
        <span class="sort-label">Sort by {$sortConfig.by}</span>
    </button>

    <button
        class="direction-btn"
        onclick={toggleDirection}
        title="Toggle sort direction"
    >
        <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            style="transform: {$sortConfig.direction === 'desc'
                ? 'rotate(180deg)'
                : 'none'};"
        >
            <path d="M12 5v14M8 11l4-4 4 4" />
        </svg>
    </button>

    {#if isOpen}
        <div class="sort-menu">
            {#each sortOptions as option}
                <button
                    class="sort-option"
                    class:active={$sortConfig.by === option.value}
                    onclick={() => setSort(option.value)}
                >
                    {option.label}
                </button>
            {/each}
        </div>
    {/if}
</div>

<style>
    .sort-container {
        position: relative;
        display: flex;
        align-items: center;
        gap: 4px;
    }

    .sort-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 6px 10px;
        background: transparent;
        border: 1px solid #ddd;
        border-radius: 4px;
        cursor: pointer;
        color: #666;
        font-size: 13px;
        transition: all 0.15s;
    }

    .sort-btn:hover {
        background-color: #f0f0f0;
        color: #fd7d05;
    }

    .sort-label {
        min-width: 60px;
        text-align: left;
    }

    .direction-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 6px;
        background: transparent;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        color: #666;
        transition: all 0.15s;
    }

    .direction-btn:hover {
        background-color: #f0f0f0;
        color: #fd7d05;
    }

    .sort-menu {
        position: absolute;
        top: 100%;
        left: 0;
        margin-top: 4px;
        background: white;
        border: 1px solid #ddd;
        border-radius: 4px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        min-width: 120px;
    }

    .sort-option {
        display: block;
        width: 100%;
        padding: 8px 16px;
        text-align: left;
        background: transparent;
        border: none;
        cursor: pointer;
        font-size: 13px;
        color: #666;
    }

    .sort-option:hover {
        background-color: #f0f0f0;
        color: #fd7d05;
    }

    .sort-option.active {
        background-color: rgba(253, 125, 5, 0.1);
        color: #fd7d05;
        font-weight: 500;
    }

    /* Dark mode */
    :global(body.dark) .sort-btn {
        border-color: #444;
        color: #b0b0b0;
    }

    :global(body.dark) .sort-btn:hover {
        background-color: #3d3d3d;
        color: #ff9f4b;
    }

    :global(body.dark) .direction-btn {
        color: #b0b0b0;
    }

    :global(body.dark) .direction-btn:hover {
        background-color: #3d3d3d;
        color: #ff9f4b;
    }

    :global(body.dark) .sort-menu {
        background: #2d2d2d;
        border-color: #444;
    }

    :global(body.dark) .sort-option {
        color: #b0b0b0;
    }

    :global(body.dark) .sort-option:hover {
        background-color: #3d3d3d;
        color: #ff9f4b;
    }

    :global(body.dark) .sort-option.active {
        background-color: rgba(255, 159, 75, 0.2);
        color: #ff9f4b;
    }
</style>
