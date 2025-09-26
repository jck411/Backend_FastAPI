<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import FilterSection from './FilterSection.svelte';

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

<FilterSection {title}>
  <div class="options">
    {#if options.length === 0}
      <p class="empty">{emptyMessage}</p>
    {:else}
      {#each options as option}
        <button
          type="button"
          aria-pressed={isSelected(option)}
          class:active={isSelected(option)}
          on:click={() => handleToggle(option)}
        >
          {option}
        </button>
      {/each}
    {/if}
  </div>
</FilterSection>

<style>
  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  button {
    border-radius: 999px;
    border: 1px solid #1f2a45;
    background: rgba(14, 20, 33, 0.9);
    color: #d4daee;
    padding: 0.35rem 0.9rem;
    font-size: 0.88rem;
    line-height: 1.3;
    min-height: 2rem;
    cursor: pointer;
    transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease;
  }

  button:hover {
    border-color: #38bdf8;
    color: #f2f7ff;
  }

  button:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  button.active {
    background: rgba(35, 60, 104, 0.85);
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .empty {
    margin: 0;
    color: #7f89a3;
    font-size: 0.9rem;
  }
</style>
