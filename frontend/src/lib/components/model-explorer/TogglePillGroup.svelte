<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let title: string;
  export let options: string[] = [];
  export let selected: string[] = [];
  export let emptyMessage = 'No options available.';

  const dispatch = createEventDispatcher<{ toggle: string }>();

  function handleToggle(value: string) {
    dispatch('toggle', value);
  }

function isSelected(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return selected.some((entry) => entry.trim().toLowerCase() === normalized);
}
</script>

<div class="filter-card">
  <header>
    <h3>{title}</h3>
  </header>
  <div class="options">
    {#if options.length === 0}
      <p class="empty">{emptyMessage}</p>
    {:else}
      {#each options as option}
        <button type="button" class:active={isSelected(option)} on:click={() => handleToggle(option)}>
          {option}
        </button>
      {/each}
    {/if}
  </div>
</div>

<style>
  .filter-card {
    border: 1px solid #1e2b46;
    border-radius: 1rem;
    padding: 1rem;
    display: grid;
    gap: 0.75rem;
    background: #10182b;
  }

  h3 {
    margin: 0;
    font-size: 1rem;
  }

  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  button {
    border-radius: 999px;
    border: 1px solid #25314d;
    background: none;
    color: inherit;
    padding: 0.35rem 0.8rem;
    cursor: pointer;
  }

  button.active {
    background: #17263f;
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .empty {
    margin: 0;
    color: #7f89a3;
    font-size: 0.9rem;
  }
</style>
