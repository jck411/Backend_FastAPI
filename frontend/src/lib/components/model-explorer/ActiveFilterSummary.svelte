<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { FilterChip } from "./types";

  export let chips: FilterChip[] = [];

  const dispatch = createEventDispatcher<{ clear: FilterChip }>();

  function handleClear(chip: FilterChip): void {
    dispatch("clear", chip);
  }
</script>

{#if chips.length > 0}
  <section class="active-filters" aria-label="Active filters">
    <h3 class="title">Active filters</h3>
    <div class="chip-list">
      {#each chips as chip (chip.id)}
        <button
          type="button"
          class="chip"
          class:include={chip.state === "include"}
          class:exclude={chip.state === "exclude"}
          on:click={() => handleClear(chip)}
          aria-label={`Remove ${chip.state === "exclude" ? "excluded" : "included"} filter ${chip.categoryLabel} ${chip.valueLabel}`}
        >
          <span class="chip-label">
            <span class="chip-category">{chip.categoryLabel}</span>
            <span class="chip-separator" aria-hidden="true">·</span>
            <span class="chip-value">
              {chip.state === "exclude" ? "Not " : ""}{chip.valueLabel}
            </span>
          </span>
          <span class="chip-remove" aria-hidden="true">×</span>
        </button>
      {/each}
    </div>
  </section>
{/if}

<style>
  .active-filters {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 0.5rem 0.25rem;
  }

  .title {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #7f89a3;
    margin: 0;
  }

  .chip-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(31, 42, 69, 0.7);
    background: rgba(14, 20, 33, 0.9);
    color: #ccd3ea;
    padding: 0.25rem 0.65rem;
    font-size: 0.78rem;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
  }

  .chip:hover {
    transform: translateY(-1px);
    border-color: #38bdf8;
  }

  .chip:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .chip:focus:not(:focus-visible) {
    outline: none;
  }

  .chip.include {
    border-color: rgba(56, 189, 248, 0.6);
    background: rgba(31, 82, 120, 0.35);
    color: #e0f2ff;
  }

  .chip.exclude {
    border-color: rgba(248, 113, 113, 0.7);
    background: rgba(110, 22, 22, 0.35);
    color: #fee2e2;
  }

  .chip-label {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }

  .chip-category {
    font-weight: 600;
  }

  .chip-value {
    font-weight: 500;
  }

  .chip-remove {
    font-size: 0.85rem;
    line-height: 1;
  }

  @media (max-width: 640px) {
    .active-filters {
      padding: 0.25rem 0;
    }

    .chip {
      font-size: 0.75rem;
    }
  }
</style>
