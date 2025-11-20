<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { Suggestion } from "../../api/types";

  const dispatch = createEventDispatcher<{
    select: { text: string };
    add: void;
    delete: { index: number };
  }>();

  export let suggestions: Suggestion[] = [];
  export let deleting: number | null = null;

  let showingAddForm = false;
  let newLabel = "";
  let newText = "";

  function handleClick(text: string): void {
    dispatch("select", { text });
  }

  function handleDelete(index: number, event: MouseEvent): void {
    event.stopPropagation();
    dispatch("delete", { index });
  }

  function handleAdd(): void {
    showingAddForm = true;
  }

  function handleAddSubmit(): void {
    if (newLabel.trim() && newText.trim()) {
      dispatch("add");
      newLabel = "";
      newText = "";
      showingAddForm = false;
    }
  }

  function handleAddCancel(): void {
    newLabel = "";
    newText = "";
    showingAddForm = false;
  }

  // Expose the new suggestion values for the parent
  export function getNewSuggestion(): { label: string; text: string } | null {
    const label = newLabel.trim();
    const text = newText.trim();
    if (label && text) {
      return { label, text };
    }
    return null;
  }
</script>

<section class="suggestions">
  {#each suggestions as prompt, index (prompt.text)}
    <div class="suggestion-item">
      <button
        type="button"
        class="suggestion-btn"
        on:click={() => handleClick(prompt.text)}
      >
        {prompt.label}
      </button>
      <button
        type="button"
        class="delete-btn"
        on:click={(e) => handleDelete(index, e)}
        disabled={deleting === index}
        title="Delete suggestion"
      >
        ×
      </button>
    </div>
  {/each}

  {#if showingAddForm}
    <div class="add-form">
      <input
        type="text"
        placeholder="Label"
        bind:value={newLabel}
        on:keydown={(e) => e.key === "Enter" && handleAddSubmit()}
      />
      <input
        type="text"
        placeholder="Prompt text"
        bind:value={newText}
        on:keydown={(e) => e.key === "Enter" && handleAddSubmit()}
      />
      <button type="button" class="add-submit-btn" on:click={handleAddSubmit}
        >Add</button
      >
      <button type="button" class="add-cancel-btn" on:click={handleAddCancel}
        >Cancel</button
      >
    </div>
  {:else}
    <button
      type="button"
      class="add-btn"
      aria-label="Add suggested prompt"
      on:click={handleAdd}
    >
      +
    </button>
  {/if}
</section>

<style>
  .suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    padding: 1.5rem 2rem;
    max-width: min(800px, 100%);
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }

  .suggestion-item {
    position: relative;
    display: inline-flex;
    align-items: center;
  }

  .suggestion-btn {
    font-size: 0.85rem;
    padding: 0.625rem 2.5rem 0.625rem 1.25rem;
    border-radius: 999px;
    background: rgba(20, 30, 51, 0.4);
    border: 1px solid rgba(57, 76, 114, 0.6);
    color: inherit;
    cursor: pointer;
    font: inherit;
  }

  .suggestion-btn:hover,
  .suggestion-btn:focus {
    border-color: rgba(140, 180, 255, 0.6);
  }

  .delete-btn {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 2rem;
    height: 2rem;
    border: none;
    background: transparent;
    color: #ff6b6b;
    cursor: pointer;
    font-size: 1.5rem;
    line-height: 1;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .delete-btn:hover:not([disabled]) {
    color: #ff4444;
  }

  .delete-btn[disabled] {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .add-btn {
    border: none;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font: inherit;
    font-size: 1.5rem;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    transition:
      transform 0.18s ease,
      color 0.18s ease;
  }

  .add-btn:hover,
  .add-btn:focus-visible {
    transform: translateY(-1px) scale(1.04);
    color: #7effb8;
    text-shadow: 0 0 6px rgba(127, 255, 184, 0.45);
  }

  .add-btn:active {
    transform: scale(0.92);
    text-shadow: none;
  }

  .add-form {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .add-form input {
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(20, 30, 51, 0.6);
    border: 1px solid rgba(57, 76, 114, 0.6);
    color: inherit;
    font: inherit;
  }

  .add-form input::placeholder {
    color: rgba(255, 255, 255, 0.4);
  }

  .add-submit-btn {
    font-size: 0.85rem;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    background: rgba(20, 80, 51, 0.4);
    border: 1px solid rgba(57, 114, 76, 0.6);
    color: #a0e0b0;
    cursor: pointer;
    font: inherit;
  }

  .add-cancel-btn {
    font-size: 0.85rem;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    background: transparent;
    border: 1px solid rgba(114, 57, 57, 0.6);
    color: #e0a0a0;
    cursor: pointer;
    font: inherit;
  }

  @media (max-width: 1050px) {
    .suggestions {
      padding: 1.25rem 1.5rem;
      gap: 0.65rem;
    }
  }
  @media (max-width: 750px) {
    .suggestions {
      padding: 1rem 1rem;
      gap: 0.5rem;
    }
    .suggestion-item {
      width: 100%;
    }
    .suggestion-btn {
      width: 100%;
      text-align: center;
    }
    .add-btn {
      width: 100%;
    }
    .add-form {
      width: 100%;
    }
    .add-form input {
      flex: 1;
      min-width: 120px;
    }
  }
  @media (max-width: 420px) {
    .suggestions {
      padding: 0.85rem 0.75rem;
      gap: 0.45rem;
    }
  }
</style>
