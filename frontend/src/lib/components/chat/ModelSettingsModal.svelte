<script lang="ts">
  import { afterUpdate, createEventDispatcher } from 'svelte';
  import type { ModelRecord } from '../../api/types';
  import ModelParameterField from './model-settings/ModelParameterField.svelte';
  import ReasoningSettingsSection from './model-settings/ReasoningSettingsSection.svelte';
  import { useModelSettings } from './model-settings/useModelSettings';
  import './model-settings/model-settings-styles.css';

  export let open = false;
  export let selectedModel = '';
  export let model: ModelRecord | null = null;

  const dispatch = createEventDispatcher<{ close: void }>();

  const {
    settingsState,
    parameters,
    fields,
    hasCustomParameters,
    reasoning,
    parameterHandlers,
    reasoningHandlers,
    resetToDefaults,
    flushSave,
    sync,
  } = useModelSettings();

  let dialogEl: HTMLElement | null = null;

  $: sync({ open, selectedModel, model });

  afterUpdate(() => {
    if (open && dialogEl) {
      dialogEl.focus();
    }
  });

  function closeModal(): void {
    void flushSave().finally(() => dispatch('close'));
  }

  function handleBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      closeModal();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeModal();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="model-settings-layer">
    <button
      type="button"
      class="model-settings-backdrop"
      aria-label="Close model settings"
      on:click={handleBackdrop}
    ></button>
    <div
      class="model-settings-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="model-settings-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="model-settings-header">
        <div class="model-settings-heading">
          <h2 id="model-settings-title">Model settings</h2>
          <p class="model-settings-subtitle">
            {#if model?.name}
              {model.name}
            {:else if model?.id}
              {model.id}
            {:else}
              {selectedModel}
            {/if}
          </p>
        </div>
        <div class="model-settings-actions">
          <button
            type="button"
            class="ghost small"
            on:click={resetToDefaults}
            disabled={!$hasCustomParameters || $settingsState.saving}
          >
            Reset to defaults
          </button>
          <button type="button" class="modal-close" on:click={closeModal} aria-label="Close">
            Close
          </button>
        </div>
      </header>
      <section class="model-settings-body">
        {#if $settingsState.loading}
          <p class="status">Loading settings…</p>
        {:else if $settingsState.error}
          <p class="status error">{$settingsState.error}</p>
        {:else}
          {#if !$reasoning.supported && !$fields.length}
            <p class="status">This model does not expose configurable parameters.</p>
          {:else}
            <div class="settings-stack" aria-live="polite">
              {#if $reasoning.supported}
                <ReasoningSettingsSection reasoning={$reasoning} handlers={reasoningHandlers} />
              {/if}

              {#if $fields.length}
                <form class="settings-grid">
                  {#each $fields as field (field.key)}
                    <ModelParameterField {field} parameters={$parameters} handlers={parameterHandlers} />
                  {/each}
                </form>
              {/if}
            </div>
          {/if}
        {/if}
      </section>
      <footer class="model-settings-footer">
        {#if $settingsState.saveError}
          <span class="status error">{$settingsState.saveError}</span>
        {:else if $settingsState.saving}
          <span class="status">Saving…</span>
        {:else if $settingsState.dirty}
          <span class="status">Pending changes…</span>
        {:else}
          <span class="status">Changes are saved automatically.</span>
        {/if}
      </footer>
    </div>
  </div>
{/if}
