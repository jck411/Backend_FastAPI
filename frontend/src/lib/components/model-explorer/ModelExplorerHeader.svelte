<script lang="ts">
  import chatArrow from "../../../assets/arrow_left_alt_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg";
  import type { ModelSort } from "../../stores/models";
  import SortControls from "./SortControls.svelte";

  export let resultCount = 0;
  export let searchValue = "";
  export let onSearch: (value: string) => void;
  export let sort: ModelSort;
  export let onSort: (value: ModelSort) => void;
  export let onClose: () => void;

  function handleSearchInput(event: Event) {
    const target = event.target as HTMLInputElement | null;
    if (!target) return;
    onSearch(target.value);
  }
</script>

<header class="explorer-header">
  <div class="title-group">
    <button
      type="button"
      class="back-btn"
      aria-label="Go back"
      on:click={onClose}
    >
      <img src={chatArrow} alt="" aria-hidden="true" class="icon" />
    </button>
    <h2 id="model-explorer-title">Model Explorer</h2>
  </div>
  <div class="header-controls">
    <label class="search">
      <span class="visually-hidden">Search models</span>
      <input
        class="input-control"
        type="search"
        placeholder="Search by name, provider, description, or tags"
        value={searchValue}
        on:input={handleSearchInput}
      />
    </label>
    <div class="meta-row">
      <p class="summary" aria-live="polite">
        {resultCount} result{resultCount === 1 ? "" : "s"}
      </p>
      <SortControls selected={sort} onSelect={onSort} />
    </div>
  </div>
</header>

<style>
  .explorer-header {
    display: grid;
    grid-template-columns: 1fr;
    align-items: start;
    row-gap: 0.75rem;
  }

  .explorer-header h2 {
    margin: 0;
  }

  .title-group {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    justify-self: start;
    flex-wrap: wrap;
  }

  .back-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.25rem;
    height: 2.25rem;
    padding: 0;
    border: 1px solid #25314d;
    border-radius: 50%;
    background: rgba(11, 17, 29, 0.9);
    color: #e3e3e3;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      transform 0.15s ease;
  }

  .back-btn:hover {
    border-color: #38bdf8;
    background: rgba(16, 25, 43, 0.95);
    transform: translateX(-2px);
  }

  .back-btn:focus-visible {
    outline: 2px solid rgba(56, 189, 248, 0.6);
    outline-offset: 2px;
  }

  .back-btn .icon {
    width: 1.25rem;
    height: 1.25rem;
    flex-shrink: 0;
    display: block;
  }

  .summary {
    margin: 0;
    color: #8a92ac;
    font-size: 0.88rem;
    white-space: nowrap;
  }

  .header-controls {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    width: min(100%, 320px);
    justify-self: start;
  }

  .search {
    width: 100%;
    min-width: 0;
  }

  .search input {
    width: 100%;
  }

  .meta-row {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    flex-wrap: nowrap;
    gap: 0.75rem;
    width: auto;
    white-space: nowrap;
  }

  .summary,
  .meta-row :global(.sort) {
    flex: 0 0 auto;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  @media (max-width: 480px) {
    .meta-row {
      gap: 0.5rem;
    }

    .summary {
      white-space: normal;
    }
  }
</style>
