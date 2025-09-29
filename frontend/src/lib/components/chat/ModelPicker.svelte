<script lang="ts">
  import { createEventDispatcher } from "svelte";

  interface SelectableModel {
    id: string;
    name?: string | null;
  }

  const dispatch = createEventDispatcher<{
    modelChange: { id: string };
    openModelSettings: void;
  }>();

  export let selectableModels: SelectableModel[] = [];
  export let selectedModel = "";
  export let modelsLoading = false;
  export let modelsError: string | null = null;

  function handleModelChange(event: Event): void {
    const target = event.target as HTMLSelectElement | null;
    if (!target) return;
    dispatch("modelChange", { id: target.value });
  }

  function handleOpenModelSettings(): void {
    dispatch("openModelSettings");
  }
</script>

<div class="model-picker">
  <select
    on:change={handleModelChange}
    bind:value={selectedModel}
    disabled={modelsLoading}
  >
    {#if modelsLoading}
      <option>Loading…</option>
    {:else if modelsError}
      <option disabled>{`Failed to load models — ${modelsError}`}</option>
    {:else if !selectableModels.length}
      <option disabled>No models</option>
    {:else}
      {#each selectableModels as model (model.id)}
        <option value={model.id}>{model.name ?? model.id}</option>
      {/each}
    {/if}
  </select>

  <button
    class="ghost"
    type="button"
    on:click={handleOpenModelSettings}
    disabled={modelsLoading || !selectedModel}
  >
    <span>Model</span>
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.89 3.31.876 2.42 2.42a1.724 1.724 0 0 0 1.066 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.572c.89 1.543-.876 3.31-2.42 2.42a1.724 1.724 0 0 0-2.572 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.89-3.31-.876-2.42-2.42a1.724 1.724 0 0 0-1.066-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.572c-.89-1.543.876-3.31 2.42-2.42.965.557 2.185.21 2.573-1.066Z"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </button>
</div>

<style>
  .model-picker {
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
  }
</style>
