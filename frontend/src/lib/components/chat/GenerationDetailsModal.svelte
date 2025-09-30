<script lang="ts">
  import { afterUpdate } from 'svelte';
  import { createEventDispatcher } from 'svelte';
  import type { GenerationDetails } from '../../api/types';
  import {
    GENERATION_DETAIL_FIELDS,
    formatGenerationDetailValue,
    type GenerationDetailDisplayValue,
  } from '../../chat/constants';
  import type { GenerationDetailField } from '../../chat/constants';

  const dispatch = createEventDispatcher<{ close: void }>();

  export let open = false;
  export let generationId: string | null = null;
  export let loading = false;
  export let error: string | null = null;
  export let data: GenerationDetails | null = null;
  export let fields: GenerationDetailField[] = GENERATION_DETAIL_FIELDS;

  let dialogEl: HTMLElement | null = null;

  afterUpdate(() => {
    if (open && dialogEl) {
      dialogEl.focus();
    }
  });

  function handleClose(): void {
    dispatch('close');
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      handleClose();
    }
  }

  interface FormattedDetail {
    field: GenerationDetailField;
    display: GenerationDetailDisplayValue;
  }

  let formattedDetails: FormattedDetail[] = [];

  $: formattedDetails = data
    ? fields.map((field) => ({
        field,
        display: formatGenerationDetailValue(data?.[field.key]),
      }))
    : [];
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="generation-modal-layer">
    <button
      type="button"
      class="generation-modal-backdrop"
      aria-label="Close generation details"
      on:click={handleClose}
    ></button>
    <div
      class="generation-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="generation-modal-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="generation-modal-header">
        <div>
          <h2 id="generation-modal-title">Generation details</h2>
          {#if generationId}
            <p class="generation-modal-subtitle">ID: {generationId}</p>
          {/if}
        </div>
        <button
          type="button"
          class="modal-close"
          on:click={handleClose}
          aria-label="Close generation details"
        >
          Close
        </button>
      </header>
      <section class="generation-modal-body">
        {#if loading}
          <p class="generation-modal-status">Loading…</p>
        {:else if error}
          <p class="generation-modal-error">{error}</p>
        {:else if data}
          <dl class="generation-modal-details">
            {#each formattedDetails as detail (detail.field.key)}
              <div class="generation-detail-row">
                <dt>{detail.field.label}</dt>
                <dd>
                  {#if detail.display.isMultiline}
                    <pre>{detail.display.text}</pre>
                  {:else}
                    {detail.display.text}
                  {/if}
                </dd>
              </div>
            {/each}
          </dl>
        {:else}
          <p class="generation-modal-status">No details available.</p>
        {/if}
      </section>
    </div>
  </div>
{/if}

<style>
  .generation-modal-layer {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    z-index: 120;
  }
  .generation-modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(4, 8, 20, 0.6);
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
  }
  .generation-modal-backdrop:focus-visible {
    outline: 2px solid #38bdf8;
  }
  .generation-modal {
    position: relative;
    width: min(520px, 100%);
    max-height: min(80vh, 640px);
    background: rgba(10, 16, 28, 0.95);
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-radius: 1rem;
    box-shadow: 0 18px 48px rgba(3, 8, 20, 0.55);
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1;
  }
  .generation-modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 1.25rem 1.5rem 1rem;
    border-bottom: 1px solid rgba(67, 91, 136, 0.45);
  }
  .generation-modal-header h2 {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
  }
  .generation-modal-subtitle {
    margin: 0.35rem 0 0;
    font-size: 0.75rem;
    color: #8ea7d2;
    word-break: break-all;
  }
  .modal-close {
    background: none;
    border: 1px solid rgba(71, 99, 150, 0.6);
    border-radius: 999px;
    color: #f3f5ff;
    padding: 0.35rem 0.9rem;
    cursor: pointer;
    font-size: 0.75rem;
  }
  .modal-close:hover,
  .modal-close:focus {
    border-color: #38bdf8;
    color: #38bdf8;
  }
  .generation-modal-body {
    padding: 1.25rem 1.5rem 1.5rem;
    overflow-y: auto;
  }
  .generation-modal-details {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }
  .generation-detail-row {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.75rem;
    border: 1px solid rgba(67, 91, 136, 0.4);
    border-radius: 0.6rem;
    background: rgba(9, 14, 26, 0.6);
  }
  .generation-detail-row dt {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #7b87a1;
  }
  .generation-detail-row dd {
    margin: 0;
    font-size: 0.9rem;
    color: #f3f5ff;
    font-weight: 500;
    word-break: break-word;
  }
  .generation-detail-row dd pre {
    margin: 0;
    white-space: pre-wrap;
    font-family: 'Fira Code', 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
    background: rgba(12, 18, 32, 0.75);
    border-radius: 0.55rem;
    padding: 0.65rem 0.75rem;
    border: 1px solid rgba(67, 91, 136, 0.25);
  }
  .generation-modal-status,
  .generation-modal-error {
    margin: 0;
    font-size: 0.9rem;
  }
  .generation-modal-error {
    color: #f87171;
  }
</style>
