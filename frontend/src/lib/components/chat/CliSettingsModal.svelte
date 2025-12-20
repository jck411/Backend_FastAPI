<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import {
    cliSettings,
    DEFAULT_CLI_SETTINGS,
    type CliSettings,
  } from "../../stores/cliSettings";
  import { modelStore } from "../../stores/models";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./model-settings/model-settings-styles.css";
  import { autoSize } from "./autoSize";
  import "./system-settings.css";

  const { filtered } = modelStore;

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  let draft: CliSettings = { ...DEFAULT_CLI_SETTINGS };
  let dirty = false;
  let saving = false;
  let loading = true;
  let statusMessage: string | null = null;
  let wasOpen = false;
  let closing = false;

  $: if (open && !wasOpen) {
    wasOpen = true;
    dirty = false;
    saving = false;
    statusMessage = null;
    void loadSettings();
  } else if (!open && wasOpen) {
    wasOpen = false;
    if (dirty && !saving) {
      void flushSave();
    }
  }

  async function loadSettings(): Promise<void> {
    loading = true;
    try {
      const [settings] = await Promise.all([
        cliSettings.load(),
        modelStore.loadModels(),
      ]);
      draft = { ...settings };
    } catch (error) {
      statusMessage = "Failed to load settings";
    } finally {
      loading = false;
    }
  }

  function closeModal(): void {
    if (closing || saving) {
      return;
    }
    closing = true;
    void (async () => {
      const success = await flushSave();
      if (success) {
        dispatch("close");
      }
      closing = false;
    })();
  }

  function markDirty(): void {
    dirty = true;
    statusMessage = null;
  }

  async function flushSave(): Promise<boolean> {
    if (!dirty) return true;

    saving = true;
    statusMessage = null;

    try {
      await cliSettings.updateLlm({
        model: draft.model,
        system_prompt: draft.system_prompt,
        temperature: draft.temperature,
        max_tokens: draft.max_tokens,
      });
      dirty = false;
      return true;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to save settings.";
      statusMessage = message;
      return false;
    } finally {
      saving = false;
    }
  }

  async function handleReset(): Promise<void> {
    saving = true;
    try {
        await cliSettings.reset();
        const settings = await cliSettings.load(); // Reload to get fresh defaults
        draft = { ...settings };
        dirty = false;
        statusMessage = null;
    } catch (error) {
      statusMessage = "Failed to reset settings";
    } finally {
      saving = false;
    }
  }

  async function handleSaveAsDefault(): Promise<void> {
    saving = true;
    try {
      // Ensure current draft is saved first
      if (dirty) {
        await flushSave();
      }
      await cliSettings.saveAsDefault();
      statusMessage = "Settings saved as new default";
    } catch (error) {
      statusMessage = "Failed to save as default";
    } finally {
      saving = false;
    }
  }

  // Calculate slider fill percentage for styling
  function getSliderFill(value: number, min: number, max: number): string {
    return `${((value - min) / (max - min)) * 100}%`;
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="cli-settings-title"
    closeLabel="Close CLI settings"
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="cli-settings-title">CLI Settings</h2>
      <p class="model-settings-subtitle">
        Configure the command-line assistant.
      </p>
    </svelte:fragment>

    <div slot="actions" style="display: flex; gap: 0.5rem;">
      <button
        type="button"
        class="btn btn-ghost btn-small"
        on:click={handleReset}
        disabled={saving || loading}
      >
        Reset to defaults
      </button>
      <button
        type="button"
        class="btn btn-primary btn-small"
        on:click={() => void handleSaveAsDefault()}
        disabled={saving || loading}
      >
        {saving ? "Saving…" : "Set as default"}
      </button>
    </div>

    {#if loading}
      <p class="status">Loading settings…</p>
    {:else}
      <div class="settings-stack" aria-live="polite">
        <!-- LLM Settings Section -->
        <div class="setting reasoning">
          <div class="setting-header">
            <span class="setting-label">Language Model</span>
            <span class="setting-hint"
              >Configure the AI model and behavior for the CLI.</span
            >
          </div>

          <div class="reasoning-controls">
            <!-- Row 1: Model Selection (Full Width for now, or compact if we add presets later) -->
            <div class="setting-select" style="grid-column: 1 / -1;">
              <label
                class="setting-label"
                for="cli-llm-model"
                title="Select the language model for CLI responses."
                >Model</label
              >
              <select
                id="cli-llm-model"
                class="select-input"
                value={draft.model}
                disabled={saving}
                on:change={(e) => {
                  draft = {
                    ...draft,
                    model: (e.target as HTMLSelectElement).value,
                  };
                  markDirty();
                }}
              >
                {#each $filtered as model (model.id)}
                  <option value={model.id}>{model.name ?? model.id}</option>
                {/each}
              </select>
            </div>

            <!-- Row 2: System Prompt -->
            <div class="system-prompt-row">
              <label
                class="setting-label"
                for="cli-system-prompt"
                title="Instructions that define how the CLI assistant behaves."
                >System Prompt</label
              >
              <textarea
                id="cli-system-prompt"
                class="keyterms-input system-prompt"
                rows="6"
                disabled={saving}
                placeholder="You are a helpful CLI assistant..."
                use:autoSize={draft.system_prompt}
                on:input={(e) => {
                  draft = {
                    ...draft,
                    system_prompt:
                      (e.target as HTMLTextAreaElement).value || null,
                  };
                  markDirty();
                }}>{draft.system_prompt ?? ""}</textarea
              >
            </div>

            <!-- Row 3: Temperature -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Controls randomness in responses."
                    >Temperature</span
                  >
                  <span class="range-value"
                    >{draft.temperature?.toFixed(1) ?? "0.7"}</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="0"
                  max="2"
                  step="0.1"
                  value={draft.temperature ?? 0.7}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.temperature ?? 0.7,
                    0,
                    2,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      temperature: parseFloat(
                        (e.target as HTMLInputElement).value,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>0 (focused)</span>
                  <span>2 (creative)</span>
                </div>
              </div>
            </div>

            <!-- Row 3: Max Tokens -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Maximum length of responses in tokens."
                    >Max Tokens</span
                  >
                  <span class="range-value">{draft.max_tokens ?? 1000}</span>
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="50"
                  max="4000"
                  step="50"
                  value={draft.max_tokens ?? 1000}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.max_tokens ?? 1000,
                    50,
                    4000,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      max_tokens: parseInt(
                        (e.target as HTMLInputElement).value,
                        10,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>50</span>
                  <span>4000</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    {/if}

    <footer slot="footer" class="model-settings-footer">
      {#if statusMessage}
        <span class="status" class:error={statusMessage.includes("Failed")}>{statusMessage}</span>
      {:else if saving}
        <span class="status">Saving changes…</span>
      {:else if dirty}
        <span class="status">Pending changes; closing this modal will save.</span>
      {:else}
        <span class="status">Changes save on close. "Set as default" updates the reset target.</span>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}

<style>
  /* Use model settings layout */
  :global(.model-settings-modal) {
    width: min(720px, 100%);
  }

  .keyterms-input {
    width: 100%;
    padding: 0.6rem 0.75rem;
    border-radius: 0.5rem;
    background-color: var(--color-surface);
    color: var(--color-text);
    border: 1px solid rgba(67, 91, 136, 0.4);
    font-family: inherit;
    font-size: 0.85rem;
    resize: vertical;
    min-height: 70px;
    line-height: 1.4;
  }

  .keyterms-input.system-prompt {
    resize: none;
    overflow: hidden;
  }

  .keyterms-input:focus {
    outline: none;
    border-color: var(--color-accent);
    box-shadow: var(--shadow-focus);
  }

  .keyterms-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .keyterms-input::placeholder {
    color: var(--color-muted);
    opacity: 0.6;
  }

  .setting-select {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .select-input {
    width: 100%;
    padding: 0.6rem 0.75rem;
    border-radius: 0.5rem;
    background-color: var(--color-surface);
    color: var(--color-text);
    border: 1px solid rgba(67, 91, 136, 0.4);
    font-family: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }

  .select-input:focus {
    outline: none;
    border-color: var(--color-accent);
    box-shadow: var(--shadow-focus);
  }

  .select-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .system-prompt-row {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
    margin-top: 0.5rem;
    grid-column: 1 / -1; /* Span full width in parent grid */
  }
</style>
