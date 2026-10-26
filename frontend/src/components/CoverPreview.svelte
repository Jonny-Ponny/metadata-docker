<!-- src/components/CoverPreview.svelte -->
<script>
  import { isRemoteImageUrl, loadPreviewImage } from "../utils/index.js";

  let {
    url = null,
    alt = "cover",
    variant = "field",
    placeholder = null,
    showSourceLink = true,
  } = $props();

  let previewSrc = $state(null);
  let loadFailed = $state(false);

  const isRemote = $derived(isRemoteImageUrl(url));
  const isDirectImage = $derived(
    typeof url === "string" &&
      (url.startsWith("data:image") || url.startsWith("blob:")),
  );
  const canLoad = $derived(isDirectImage || isRemote);
  const showPlaceholder = $derived(
    !!placeholder && (!url || !canLoad || loadFailed),
  );

  $effect(() => {
    let active = true;
    previewSrc = null;
    loadFailed = false;

    if (!url || !canLoad) {
      return;
    }

    if (!isRemote) {
      previewSrc = url;
      return;
    }

    loadPreviewImage(url)
      .then((src) => {
        if (active) previewSrc = src;
      })
      .catch(() => {
        if (active) loadFailed = true;
      });

    return () => {
      active = false;
    };
  });
</script>

<div class="cover-preview {variant}" title={isRemote ? url : undefined}>
  {#if previewSrc}
    <img src={previewSrc} {alt} class="cover-image" />
  {:else if showPlaceholder}
    <img src={placeholder} {alt} class="cover-image" />
  {:else if loadFailed}
    <span class="cover-failed" role="img" aria-label="Cover preview unavailable"
      >!</span
    >
  {:else}
    <span class="cover-loading" aria-hidden="true"></span>
  {/if}

  {#if isRemote && url && showSourceLink}
    <a
      class="cover-source"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="Open cover source in a new tab"
      aria-label={`Open cover source in a new tab: ${url}`}
      onclick={(event) => event.stopPropagation()}
    >
      <svg
        viewBox="0 0 24 24"
        width="12"
        height="12"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        aria-hidden="true"
      >
        <path d="M10 13a5 5 0 0 0 7.07 0l2.12-2.12a5 5 0 0 0-7.07-7.07L11 5" />
        <path
          d="M14 11a5 5 0 0 0-7.07 0L4.81 13.12a5 5 0 0 0 7.07 7.07L13 19"
        />
      </svg>
    </a>
  {/if}
</div>

<style>
  .cover-preview {
    position: relative;
    display: inline-flex;
    flex-shrink: 0;
    border-radius: 4px;
    vertical-align: middle;
  }

  .cover-preview.result {
    width: 40px;
    height: 40px;
    margin-left: 8px;
  }

  .cover-preview.field {
    width: 80px;
    height: 80px;
  }

  .cover-image {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 4px;
  }

  .cover-preview.field .cover-image {
    object-fit: contain;
    background: #fafafa;
  }

  .cover-loading,
  .cover-failed {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    border-radius: 4px;
    background: #f0f0f0;
  }

  .cover-loading {
    animation: cover-pulse 1.2s ease-in-out infinite;
  }

  .cover-failed {
    color: #999;
    font-weight: 600;
  }

  @keyframes cover-pulse {
    0%,
    100% {
      opacity: 0.55;
    }
    50% {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .cover-loading {
      animation: none;
    }
  }

  .cover-source {
    position: absolute;
    top: 2px;
    right: 2px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.65);
    color: #fff;
    opacity: 0;
    transition: opacity 0.15s ease;
  }

  .cover-preview:hover .cover-source,
  .cover-source:focus-visible {
    opacity: 1;
  }

  /* Touch devices have no hover, so keep the source link discoverable. */
  @media (hover: none) {
    .cover-source {
      width: 22px;
      height: 22px;
      opacity: 0.9;
    }
  }

  :global(body.dark) .cover-loading,
  :global(body.dark) .cover-failed {
    background: #2a2a2a;
  }

  :global(body.dark) .cover-preview.field .cover-image {
    background: #1e1e1e;
  }

  :global(body.dark) .cover-failed {
    color: #888;
  }
</style>
