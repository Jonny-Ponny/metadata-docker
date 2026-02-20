<!-- src/components/ToastContainer.svelte -->
<script>
  import Toast from "./Toast.svelte";
  import { toast } from "../utils/index.js";

  let toasts = $state([]);

  // Subscribe to toast store
  toast.subscribe(value => {
    toasts = value;
  });

  // Expose methods for backward compatibility if needed
  export function show(message, type = "info", duration = 5000) {
    return toast.show(message, type, duration);
  }

  export function success(message, duration = 5000) {
    return toast.success(message, duration);
  }

  export function error(message, duration = 5000) {
    return toast.error(message, duration);
  }

  export function warning(message, duration = 5000) {
    return toast.warning(message, duration);
  }

  export function info(message, duration = 5000) {
    return toast.info(message, duration);
  }

  export function clear() {
    toast.clear();
  }
</script>

{#if toasts.length > 0}
  <div class="toast-container">
    {#each toasts as t (t.id)}
      <Toast
        message={t.message}
        type={t.type}
        duration={t.duration}
        onDismiss={() => toast.remove(t.id)}
      />
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 99999;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 10px;
    pointer-events: none;
  }
</style>