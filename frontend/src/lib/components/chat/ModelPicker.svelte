<script lang="ts">
  import { createEventDispatcher } from "svelte";

  interface SelectableModel {
    id: string;
    name?: string | null;
  }

  const dispatch = createEventDispatcher<{
    modelChange: { id: string };
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

</script>

<div class="model-picker">
  <select
    class="select-control"
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
</div>

<style>
  .model-picker {
    display: inline-flex;
    align-items: center;
  }
</style>
