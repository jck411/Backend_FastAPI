<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import FilterSection from "./FilterSection.svelte";

  type ToggleVariant = "default" | "columns" | "compact";

  export let title: string;
  export let options: string[] = [];
  export let selected: string[] = [];
  export let emptyMessage = "No options available.";
  export let variant: ToggleVariant = "default";

  const dispatch = createEventDispatcher<{ toggle: string }>();

  function handleToggle(value: string) {
    dispatch("toggle", value);
  }

  function isSelected(value: string): boolean {
    const normalized = value.trim().toLowerCase();
    return selected.some((entry) => entry.trim().toLowerCase() === normalized);
  }
</script>

<FilterSection {title} forceOpen={selected.length > 0}>
  <div class="options" data-variant={variant}>
    {#if options.length === 0}
      <p class="empty">{emptyMessage}</p>
    {:else}
      {#each options as option}
        <button
          type="button"
          class="pill"
          class:active={isSelected(option)}
          aria-pressed={isSelected(option)}
          on:click={() => handleToggle(option)}
        >
          <span class="label">{option}</span>
          <span class="indicator" aria-hidden="true"></span>
        </button>
      {/each}
    {/if}
  </div>
</FilterSection>

<style>
  .options {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    align-items: start;
  }

  .options[data-variant="columns"] {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .options[data-variant="compact"] {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .pill {
    border-radius: 0.5rem;
    border: 1px solid rgba(31, 42, 69, 0.65);
    background: rgba(14, 20, 33, 0.9);
    color: #d4daee;
    padding: 0.45rem 0.75rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    width: 100%;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
    text-align: left;
  }

  .options[data-variant="compact"] .pill {
    width: auto;
    padding: 0.3rem 0.65rem;
    border-radius: 999px;
    gap: 0.5rem;
  }

  .pill .label {
    flex: 1;
    white-space: normal;
  }

  .indicator {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: #38bdf8;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .pill:hover {
    border-color: #38bdf8;
    color: #f2f7ff;
    transform: translateY(-1px);
  }

  .pill:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .pill:focus:not(:focus-visible) {
    outline: none;
  }

  .pill.active {
    background: rgba(35, 60, 104, 0.85);
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .pill.active .indicator {
    opacity: 1;
  }

  .options[data-variant="compact"] .indicator {
    display: none;
  }

  .options[data-variant="compact"] .pill.active {
    background: rgba(56, 189, 248, 0.15);
  }

  .empty {
    margin: 0;
    color: #7f89a3;
    font-size: 0.9rem;
  }

  @media (max-width: 900px) {
    .options {
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }
  }

  @media (max-width: 480px) {
    .options {
      grid-template-columns: 1fr;
    }
  }
</style>
