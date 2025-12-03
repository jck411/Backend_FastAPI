<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { ModelRecord } from '../../api/types';
  import ModelParameterField from './model-settings/ModelParameterField.svelte';
  import ReasoningSettingsSection from './model-settings/ReasoningSettingsSection.svelte';
  import { useModelSettings } from './model-settings/useModelSettings';
  import ModelSettingsDialog from './model-settings/ModelSettingsDialog.svelte';

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

  let closing = false;

  $: sync({ open, selectedModel, model });

  async function closeModal(): Promise<void> {
    if (closing || $settingsState.saving) {
      return;
    }
    closing = true;
    const success = await flushSave();
    if (success) {
      dispatch('close');
    }
    closing = false;
  }
</script>
{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="model-settings-title"
    closeLabel="Close model settings"
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
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
    </svelte:fragment>

    <button
      slot="actions"
      type="button"
      class="btn btn-ghost btn-small"
      on:click={resetToDefaults}
      disabled={!$hasCustomParameters || $settingsState.saving}
    >
      Reset to defaults
    </button>

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

    <footer slot="footer" class="model-settings-footer">
      {#if $settingsState.saveError}
        <span class="status error">{$settingsState.saveError}</span>
      {:else if $settingsState.saving}
        <span class="status">Saving changes…</span>
      {:else if $settingsState.dirty}
        <span class="status">Pending changes; closing this modal will save.</span>
      {:else}
        <span class="status">Changes save when you close this modal.</span>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
