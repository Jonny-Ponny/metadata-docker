<!-- src/components/TreeNode.svelte -->
<script>
    // VS Code doesnt like this
    // @ts-ignore
    import Self from "./TreeNode.svelte";

    let { item, expanded, toggleDir, selectFile, level = 0 } = $props();

    function handleDirectoryClick() {
        toggleDir(item.path);
    }

    function handleFileClick() {
        selectFile(item.path);
    }
</script>

{#if item.type === "directory"}
    <li>
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <div
            role="listitem"
            class="directory"
            class:indented={level > 0}
            style="--level: {level}"
            onclick={handleDirectoryClick}
        >
            <span class="toggle">
                {#if expanded.has(item.path)}
                    <!-- Folder open icon -->
                    <svg
                        width="16"
                        height="16"
                        viewBox="0 0 16 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                    >
                        <path
                            d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                            fill="currentColor"
                            fill-opacity="0.9"
                        />
                        <path
                            d="M3 3C2.44772 3 2 3.44772 2 4V11C2 11.5523 2.44772 12 3 12H13C13.5523 12 14 11.5523 14 11V6C14 5.44772 13.5523 5 13 5H8L6.5 3H3Z"
                            stroke="currentColor"
                            stroke-width="0.8"
                        />
                    </svg>
                {:else}
                    <!-- Folder closed icon -->
                    <svg
                        width="16"
                        height="16"
                        viewBox="0 0 16 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                    >
                        <path
                            d="M2 4.5C2 3.94772 2.44772 3.5 3 3.5H6.5L8 5.5H13C13.5523 5.5 14 5.94772 14 6.5V11.5C14 12.0523 13.5523 12.5 13 12.5H3C2.44772 12.5 2 12.0523 2 11.5V4.5Z"
                            fill="currentColor"
                            fill-opacity="0.9"
                        />
                    </svg>
                {/if}
            </span>
            <span class="name">{item.name}</span>
        </div>
        {#if expanded.has(item.path) && item.children?.length}
            <ul>
                {#each item.children as child (child.path)}
                    <Self
                        item={child}
                        {expanded}
                        {toggleDir}
                        {selectFile}
                        level={level + 1}
                    />
                {/each}
            </ul>
        {/if}
    </li>
{:else}
    <li>
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <div
            role="listitem"
            class="file"
            class:indented={level > 0}
            style="--level: {level}"
            onclick={handleFileClick}
        >
            <span class="file-icon">
                <!-- File icon -->
                <svg
                    width="14"
                    height="16"
                    viewBox="0 0 14 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                >
                    <path
                        d="M2 1.5C2 1.22386 2.22386 1 2.5 1H9.5C9.77614 1 10 1.22386 10 1.5V3.5C10 3.77614 10.2239 4 10.5 4H12.5C12.7761 4 13 4.22386 13 4.5V14.5C13 14.7761 12.7761 15 12.5 15H2.5C2.22386 15 2 14.7761 2 14.5V1.5Z"
                        fill="currentColor"
                        fill-opacity="0.7"
                    />
                    <path
                        d="M10 1L12 3H10V1Z"
                        fill="currentColor"
                        fill-opacity="0.7"
                    />
                </svg>
            </span>
            <span class="name">{item.name}</span>
            <span class="size">({(item.size / 1024).toFixed(0)} KB)</span>
        </div>
    </li>
{/if}

<style>
    li {
        list-style: none;
        margin: 2px 0;
    }

    .directory,
    .file {
        padding: 8px 12px;
        cursor: pointer;
        border-radius: 4px;
        display: flex;
        align-items: center;
        transition: background-color 0.15s;
        position: relative;
        gap: 8px;
    }

    /* Visual indentation lines */
    /* .directory.indented::before,
    .file.indented::before {
        content: "";
        position: absolute;
        left: calc(calc(var(--level) * 20px) - 8px);
        top: 0;
        bottom: 0;
        width: 2px;
        background: linear-gradient(to bottom, #ddd, transparent 80%);
        opacity: 0.5;
    } */

    .directory:hover,
    .file:hover {
        background-color: #f5f5f5;
    }

    .directory .toggle,
    .file .file-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        color: #fd7d05;
    }

    .file .file-icon {
        color: #888;
    }

    .directory .name {
        font-weight: 500;
        color: #333;
    }

    .file .name {
        flex: 1;
        color: #555;
    }

    .file .size {
        color: #888;
        font-size: 12px;
        margin-left: 8px;
    }

    /* Dark mode overrides */
    :global(body.dark) .directory .name,
    :global(body.dark) .file .name {
        color: #e0e0e0;
    }

    :global(body.dark) .file .size {
        color: #808080;
    }

    :global(body.dark) .directory:hover,
    :global(body.dark) .file:hover {
        background-color: #3d3d3d;
    }

    :global(body.dark) .directory .toggle {
        color: #ff9f4b;
    }

    :global(body.dark) .file .file-icon {
        color: #aaa;
    }

    /* Dark mode indentation lines */
    /* :global(body.dark) .directory.indented::before,
    :global(body.dark) .file.indented::before {
        background: #555;
    } */
</style>
