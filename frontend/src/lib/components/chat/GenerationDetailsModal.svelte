<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { GenerationDetails } from '../../api/types';
  import {
    GENERATION_DETAIL_FIELDS,
    formatGenerationDetailValue,
    type GenerationDetailDisplayValue,
  } from '../../chat/constants';
  import type { GenerationDetailField } from '../../chat/constants';
  import ModelSettingsDialog from './model-settings/ModelSettingsDialog.svelte';

  const dispatch = createEventDispatcher<{ close: void }>();

  export let open = false;
  export let generationId: string | null = null;
  export let loading = false;
  export let error: string | null = null;
  export let data: GenerationDetails | null = null;
  export let fields: GenerationDetailField[] = GENERATION_DETAIL_FIELDS;

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

  function handleClose(): void {
    dispatch('close');
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="generation-modal-title"
    modalClass="generation-modal"
    closeLabel="Close generation details"
    on:close={handleClose}
  >
    <svelte:fragment slot="heading">
      <h2 id="generation-modal-title">Generation details</h2>
      {#if generationId}
        <p class="model-settings-subtitle">ID: {generationId}</p>
      {/if}
    </svelte:fragment>

    {#if loading}
      <p class="status">Loading…</p>
    {:else if error}
      <p class="status error">{error}</p>
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
      <p class="status">No details available.</p>
    {/if}
  </ModelSettingsDialog>
{/if}

<style>
:global(.generation-modal) {
    width: min(520px, 100%);
    max-height: min(80vh, 640px);
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
    font-family: var(--font-mono);
    background: rgba(12, 18, 32, 0.75);
    border-radius: 0.55rem;
    padding: 0.65rem 0.75rem;
    border: 1px solid rgba(67, 91, 136, 0.25);
  }
</style>
