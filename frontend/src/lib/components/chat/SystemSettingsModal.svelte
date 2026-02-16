<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { get } from "svelte/store";
  import { fetchSttSettings, updateSttSettings } from "../../api/client";
  import type { PresetListItem } from "../../api/types";
  import { STT_MODELS, type SttSettings } from "../../api/types";
  import { chatStore } from "../../stores/chat";
  import { modelSettingsStore } from "../../stores/modelSettings";
  import { presetsStore } from "../../stores/presets";
  import {
    SPEECH_TIMING_PRESETS,
    type SpeechSettings,
    type SpeechTimingPresetKey,
    getDefaultSpeechSettings,
    speechSettingsStore,
  } from "../../stores/speechSettings";
  import { suggestionsStore } from "../../stores/suggestions";
  import { createSystemPromptStore } from "../../stores/systemPrompt";
  import { autoSize } from "./autoSize";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./presets-settings.css";
  import "./speech-settings.css";
  import "./system-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const systemPrompt = createSystemPromptStore();

  let hasInitialized = false;
  let closing = false;

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
      resetSpeechState();
      resetPresetDraft();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      systemPrompt.reset();
      resetSpeechState();
      resetPresetDraft();
    }
  }

  async function initialize(): Promise<void> {
    await Promise.all([
      systemPrompt.load(),
      presetsStore.load(),
      loadServerSttSettings(),
    ]);
  }

  async function loadServerSttSettings(): Promise<void> {
    try {
      serverSttSettings = await fetchSttSettings();
      serverSttError = null;
    } catch (error) {
      serverSttError =
        error instanceof Error ? error.message : "Failed to load STT settings";
    }
  }

  async function flushSystemPrompt(): Promise<boolean> {
    const state = get(systemPrompt);
    if (!state.dirty) {
      return true;
    }
    await systemPrompt.save();
    const latest = get(systemPrompt);
    return !latest.saveError;
  }

  async function closeModal(): Promise<void> {
    if (closing || $systemPrompt.saving || speechSaving || serverSttSaving) {
      return;
    }

    closing = true;

    const promptSaved = await flushSystemPrompt();
    const speechSaved = await flushSpeechSettings();
    const serverSttSaved = await flushServerSttSettings();

    const promptState = get(systemPrompt);

    if (
      promptSaved &&
      speechSaved &&
      serverSttSaved &&
      !promptState.saveError
    ) {
      dispatch("close");
    }

    closing = false;
  }

  async function flushServerSttSettings(): Promise<boolean> {
    if (!serverSttDirty || !serverSttSettings) {
      return true;
    }

    serverSttSaving = true;
    try {
      serverSttSettings = await updateSttSettings({
        mode: serverSttSettings.mode,
        // Command mode (Nova) settings
        command_model: serverSttSettings.command_model,
        command_utterance_end_ms: serverSttSettings.command_utterance_end_ms,
        command_endpointing: serverSttSettings.command_endpointing,
        command_interim_results: serverSttSettings.command_interim_results,
        command_smart_format: serverSttSettings.command_smart_format,
        command_numerals: serverSttSettings.command_numerals,
        // Conversation mode (Flux) settings
        eot_threshold: serverSttSettings.eot_threshold,
        eot_timeout_ms: serverSttSettings.eot_timeout_ms,
      });
      serverSttDirty = false;
      serverSttError = null;
      return true;
    } catch (error) {
      serverSttError =
        error instanceof Error ? error.message : "Failed to save STT settings";
      return false;
    } finally {
      serverSttSaving = false;
    }
  }

  let creatingName = "";
  let confirmingDelete: string | null = null;
  let speechDraft: SpeechSettings = initializeSpeechDraft();
  let speechDirty = false;
  let speechSaving = false;
  let speechSaveError: string | null = null;

  // Server-side STT settings (mode, model)
  let serverSttSettings: SttSettings | null = null;
  let serverSttDirty = false;
  let serverSttSaving = false;
  let serverSttError: string | null = null;

  function handlePromptInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    systemPrompt.updateValue(target?.value ?? "");
  }

  function resetPresetDraft(): void {
    creatingName = "";
    confirmingDelete = null;
  }

  async function handleCreatePreset(): Promise<void> {
    const name = creatingName.trim();
    if (!name) return;
    const promptSaved = await flushSystemPrompt();
    if (!promptSaved) {
      return;
    }
    await modelSettingsStore.load($chatStore.selectedModel);
    const result = await presetsStore.create(name);
    if (result) {
      creatingName = "";
    }
  }

  async function handleApplyPreset(item: PresetListItem): Promise<void> {
    const result = await presetsStore.apply(item.name);
    if (result?.model) {
      chatStore.setModel(result.model);
    }
    await suggestionsStore.load();
    dispatch("close");
  }

  async function handleSaveSnapshot(item: PresetListItem): Promise<void> {
    const promptSaved = await flushSystemPrompt();
    if (!promptSaved) {
      return;
    }
    await modelSettingsStore.load($chatStore.selectedModel);
    await presetsStore.saveSnapshot(item.name);
  }

  async function handleDeletePreset(item: PresetListItem): Promise<void> {
    if (item.is_default) {
      return;
    }
    if (confirmingDelete === item.name) {
      await presetsStore.remove(item.name);
      confirmingDelete = null;
      return;
    }
    confirmingDelete = item.name;
    setTimeout(() => {
      if (confirmingDelete === item.name) {
        confirmingDelete = null;
      }
    }, 3000);
  }

  async function handleSetDefaultPreset(item: PresetListItem): Promise<void> {
    await presetsStore.setDefault(item.name);
  }

  function initializeSpeechDraft(): SpeechSettings {
    const current = speechSettingsStore.current ?? getDefaultSpeechSettings();
    return {
      ...current,
      stt: { ...current.stt },
    };
  }

  function resetSpeechState(): void {
    speechSettingsStore.refresh();
    speechDraft = initializeSpeechDraft();
    speechDirty = false;
    speechSaving = false;
    speechSaveError = null;
    // Reset server STT state
    serverSttSettings = null;
    serverSttDirty = false;
    serverSttSaving = false;
    serverSttError = null;
  }

  function updateSpeechStt<K extends keyof SpeechSettings["stt"]>(
    key: K,
    value: SpeechSettings["stt"][K],
  ): void {
    speechDraft = {
      ...speechDraft,
      stt: {
        ...speechDraft.stt,
        [key]: value,
      },
    };
    speechDirty = true;
    speechSaveError = null;
  }

  function handleSpeechNumberInput(
    event: Event,
    updater: (value: number) => void,
  ): void {
    const target = event.target as HTMLInputElement | null;
    if (!target) {
      return;
    }
    const parsed = Number(target.value);
    if (!Number.isFinite(parsed)) {
      return;
    }
    updater(parsed);
  }

  function applySpeechPreset(key: SpeechTimingPresetKey): void {
    const preset = SPEECH_TIMING_PRESETS[key];
    speechDraft = {
      ...speechDraft,
      stt: {
        ...speechDraft.stt,
        autoSubmitDelayMs: preset.autoSubmitDelayMs,
      },
    };
    speechDirty = true;
    speechSaveError = null;
  }

  async function flushSpeechSettings(): Promise<boolean> {
    if (!speechDirty) {
      return true;
    }

    speechSaving = true;
    try {
      const saved = speechSettingsStore.save(speechDraft);
      speechDraft = {
        ...saved,
        stt: { ...saved.stt },
      };
      speechDirty = false;
      speechSaveError = null;
      return true;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to save speech settings.";
      speechSaveError = message;
      return false;
    } finally {
      speechSaving = false;
    }
  }

  function handleSpeechReset(): void {
    speechDraft = getDefaultSpeechSettings();
    speechDirty = true;
    speechSaveError = null;
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="system-settings-title"
    modalClass="system-settings-modal"
    bodyClass="system-settings-body"
    layerClass="system-settings-layer"
    closeLabel="Close system settings"
    closeDisabled={$systemPrompt.saving || speechSaving}
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="system-settings-title">System settings</h2>
      <p class="model-settings-subtitle">
        Configure orchestration defaults, presets, and speech settings.
      </p>
    </svelte:fragment>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>System prompt</h3>
          <p class="system-card-caption">
            Applied to new chat sessions when no custom prompt is present.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-ghost btn-small"
            on:click={() => systemPrompt.reset()}
            disabled={!$systemPrompt.dirty || $systemPrompt.saving}
          >
            Reset
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if $systemPrompt.loading}
          <p class="status">Loading system prompt…</p>
        {:else if $systemPrompt.error}
          <p class="status error">{$systemPrompt.error}</p>
        {:else}
          <textarea
            class="system-prompt textarea-control"
            rows="6"
            bind:value={$systemPrompt.value}
            on:input={handlePromptInput}
            placeholder="Provide guidance for the assistant to follow at the start of new conversations."
            disabled={$systemPrompt.saving}
            use:autoSize={$systemPrompt.value}
          ></textarea>
          {#if $systemPrompt.saveError}
            <p class="status error">{$systemPrompt.saveError}</p>
          {/if}
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Presets</h3>
          <p class="system-card-caption">
            Save and manage snapshots of the current configuration.
          </p>
        </div>
      </header>

      <div class="system-card-body">
        <div class="create-row">
          <input
            type="text"
            class="input-control"
            placeholder="Preset name"
            bind:value={creatingName}
            aria-label="Preset name"
            on:keydown={(event) =>
              event.key === "Enter" ? handleCreatePreset() : null}
          />
          <button
            type="button"
            class="btn btn-primary"
            on:click={handleCreatePreset}
            disabled={!creatingName.trim() || $presetsStore.creating}
            aria-busy={$presetsStore.creating}
          >
            {$presetsStore.creating ? "Creating…" : "Create from current"}
          </button>
        </div>

        {#if $presetsStore.error}
          <p class="status error">{$presetsStore.error}</p>
        {/if}

        {#if $presetsStore.loading}
          <p class="status">Loading presets…</p>
        {:else if !$presetsStore.items.length}
          <p class="status">No presets saved yet.</p>
        {:else}
          <ul class="preset-list" aria-live="polite">
            {#each $presetsStore.items as item (item.name)}
              <li class="preset-item">
                <div class="meta">
                  <div class="name">
                    {item.name}
                    {#if item.is_default}
                      <span class="default-badge" title="Default preset"
                        >Default</span
                      >
                    {/if}
                    {#if item.has_filters}
                      <span
                        class="filters-badge"
                        title="Contains model explorer filters"
                      >
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        >
                          <polygon
                            points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                          ></polygon>
                        </svg>
                        Filters
                      </span>
                    {/if}
                  </div>
                  <div class="details">
                    <span class="model">{item.model}</span>
                    <span class="timestamps">
                      <span title="Created at"
                        >{new Date(item.created_at).toLocaleString()}</span
                      >
                      <span aria-hidden="true">·</span>
                      <span title="Updated at"
                        >{new Date(item.updated_at).toLocaleString()}</span
                      >
                    </span>
                  </div>
                </div>
                <div class="actions">
                  <button
                    type="button"
                    class="btn btn-ghost btn-small"
                    on:click={() => handleApplyPreset(item)}
                    disabled={$presetsStore.applying === item.name}
                    aria-busy={$presetsStore.applying === item.name}
                    title="Apply this preset (model, settings, system prompt, MCP servers)"
                  >
                    {$presetsStore.applying === item.name
                      ? "Applying…"
                      : "Apply"}
                  </button>
                  <button
                    type="button"
                    class="btn btn-ghost btn-small"
                    on:click={() => handleSaveSnapshot(item)}
                    disabled={$presetsStore.saving}
                    aria-busy={$presetsStore.saving}
                    title="Overwrite preset with current configuration"
                  >
                    {$presetsStore.saving ? "Saving…" : "Save snapshot"}
                  </button>
                  {#if !item.is_default}
                    <button
                      type="button"
                      class="btn btn-ghost btn-small"
                      on:click={() => handleSetDefaultPreset(item)}
                      disabled={$presetsStore.settingDefault === item.name}
                      aria-busy={$presetsStore.settingDefault === item.name}
                      title="Set as default preset to load on startup"
                    >
                      {$presetsStore.settingDefault === item.name
                        ? "Setting…"
                        : "Set as default"}
                    </button>
                  {/if}
                  <button
                    type="button"
                    class="btn btn-danger btn-small"
                    on:click={() => handleDeletePreset(item)}
                    disabled={item.is_default ||
                      $presetsStore.deleting === item.name}
                    aria-busy={$presetsStore.deleting === item.name}
                    title={item.is_default
                      ? "Cannot delete default preset"
                      : "Delete preset"}
                  >
                    {confirmingDelete === item.name
                      ? "Confirm delete"
                      : $presetsStore.deleting === item.name
                        ? "Deleting…"
                        : "Delete"}
                  </button>
                </div>
              </li>
            {/each}
          </ul>
        {/if}

        {#if $presetsStore.lastApplied}
          <p class="status muted">
            Applied preset: {$presetsStore.lastApplied}
          </p>
        {:else if $presetsStore.lastResult}
          <p class="status muted">Saved: {$presetsStore.lastResult.name}</p>
        {:else}
          <p class="status muted">Create, update, or apply a preset.</p>
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Speech recognition</h3>
          <p class="system-card-caption">
            Configure speech-to-text engine and behavior.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-ghost btn-small"
            on:click={handleSpeechReset}
            disabled={speechSaving || serverSttSaving}
          >
            Reset to defaults
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if serverSttError}
          <p class="status error">{serverSttError}</p>
        {:else if !serverSttSettings}
          <p class="status">Loading STT settings…</p>
        {:else}
          <!-- Mode Selection -->
          <div class="speech-field">
            <label class="field-label" for="stt-mode-select"
              >Recognition mode</label
            >
            <select
              id="stt-mode-select"
              class="input-control"
              value={serverSttSettings.mode}
              disabled={serverSttSaving}
              on:change={(event) => {
                if (serverSttSettings) {
                  serverSttSettings = {
                    ...serverSttSettings,
                    mode: (event.target as HTMLSelectElement).value as
                      | "conversation"
                      | "command",
                  };
                  serverSttDirty = true;
                }
              }}
            >
              <option value="conversation">Conversation (Flux)</option>
              <option value="command">Command (Nova)</option>
            </select>
            <p class="speech-hint">
              {#if serverSttSettings.mode === "conversation"}
                AI-based turn detection for natural dialogue. Auto-submits when
                you finish speaking.
              {:else}
                Silence-based detection with specialized vocabulary models.
              {/if}
            </p>
          </div>

          {#if serverSttSettings.mode === "command"}
            <!-- Nova Model Selection -->
            <div class="speech-field">
              <label class="field-label" for="stt-model-select">Model</label>
              <select
                id="stt-model-select"
                class="input-control"
                value={serverSttSettings.command_model}
                disabled={serverSttSaving}
                on:change={(event) => {
                  if (serverSttSettings) {
                    serverSttSettings = {
                      ...serverSttSettings,
                      command_model: (event.target as HTMLSelectElement).value,
                    };
                    serverSttDirty = true;
                  }
                }}
              >
                {#each STT_MODELS as model (model.id)}
                  <option value={model.id}>{model.name}</option>
                {/each}
              </select>
            </div>

            <!-- Nova timing settings -->
            <div class="speech-field-row">
              <div class="speech-field">
                <label class="field-label" for="stt-utterance-end"
                  >Utterance end (ms)</label
                >
                <input
                  id="stt-utterance-end"
                  class="input-control"
                  type="number"
                  min="500"
                  max="5000"
                  step="100"
                  value={serverSttSettings.command_utterance_end_ms}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        command_utterance_end_ms: Number(
                          (event.target as HTMLInputElement).value,
                        ),
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <p class="speech-hint">Silence duration to end utterance</p>
              </div>

              <div class="speech-field">
                <label class="field-label" for="stt-endpointing"
                  >Endpointing (ms)</label
                >
                <input
                  id="stt-endpointing"
                  class="input-control"
                  type="number"
                  min="10"
                  max="5000"
                  step="50"
                  value={serverSttSettings.command_endpointing}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        command_endpointing: Number(
                          (event.target as HTMLInputElement).value,
                        ),
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <p class="speech-hint">Threshold for segment boundaries</p>
              </div>
            </div>

            <!-- Nova feature toggles -->
            <div class="speech-toggles">
              <label class="toggle">
                <input
                  type="checkbox"
                  checked={serverSttSettings.command_smart_format}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        command_smart_format: (event.target as HTMLInputElement)
                          .checked,
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <span>Smart format</span>
              </label>

              <label class="toggle">
                <input
                  type="checkbox"
                  checked={serverSttSettings.command_numerals}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        command_numerals: (event.target as HTMLInputElement)
                          .checked,
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <span>Numbers as digits</span>
              </label>

              <label class="toggle">
                <input
                  type="checkbox"
                  checked={serverSttSettings.command_interim_results}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        command_interim_results: (
                          event.target as HTMLInputElement
                        ).checked,
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <span>Interim results</span>
              </label>
            </div>

            <!-- Auto-submit toggle -->
            <div class="speech-field">
              <label class="inline-checkbox">
                <input
                  class="input-control"
                  type="checkbox"
                  checked={speechDraft.stt.autoSubmit}
                  on:change={(event) =>
                    updateSpeechStt(
                      "autoSubmit",
                      (event.target as HTMLInputElement).checked,
                    )}
                />
                <span class="field-label">Auto-submit after speaking</span>
              </label>
            </div>

            {#if speechDraft.stt.autoSubmit}
              <!-- Timing presets and custom delay -->
              <div class="speech-field">
                <label class="field-label" for="auto-submit-delay-input"
                  >Submit delay (ms)</label
                >
                <div class="delay-row">
                  <div class="delay-presets">
                    <button
                      class="btn btn-soft btn-small"
                      type="button"
                      on:click={() => applySpeechPreset("fast")}>Instant</button
                    >
                    <button
                      class="btn btn-soft btn-small"
                      type="button"
                      on:click={() => applySpeechPreset("normal")}
                      >Normal</button
                    >
                    <button
                      class="btn btn-soft btn-small"
                      type="button"
                      on:click={() => applySpeechPreset("slow")}>Slow</button
                    >
                  </div>
                  <input
                    id="auto-submit-delay-input"
                    class="input-control delay-input"
                    type="number"
                    min="0"
                    max="10000"
                    step="50"
                    value={speechDraft.stt.autoSubmitDelayMs}
                    on:change={(event) =>
                      handleSpeechNumberInput(event, (value) =>
                        updateSpeechStt("autoSubmitDelayMs", value),
                      )}
                  />
                </div>
              </div>
            {/if}
          {:else}
            <!-- Conversation mode (Flux) settings -->
            <div class="speech-field-row">
              <div class="speech-field">
                <label class="field-label" for="stt-eot-threshold"
                  >EOT threshold</label
                >
                <input
                  id="stt-eot-threshold"
                  class="input-control"
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={serverSttSettings.eot_threshold}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        eot_threshold: Number(
                          (event.target as HTMLInputElement).value,
                        ),
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <p class="speech-hint">End-of-turn confidence (0–1)</p>
              </div>

              <div class="speech-field">
                <label class="field-label" for="stt-eot-timeout"
                  >EOT timeout (ms)</label
                >
                <input
                  id="stt-eot-timeout"
                  class="input-control"
                  type="number"
                  min="100"
                  max="30000"
                  step="100"
                  value={serverSttSettings.eot_timeout_ms}
                  disabled={serverSttSaving}
                  on:change={(event) => {
                    if (serverSttSettings) {
                      serverSttSettings = {
                        ...serverSttSettings,
                        eot_timeout_ms: Number(
                          (event.target as HTMLInputElement).value,
                        ),
                      };
                      serverSttDirty = true;
                    }
                  }}
                />
                <p class="speech-hint">Max wait for turn end</p>
              </div>
            </div>

            <p class="speech-hint">
              Flux uses AI-based turn detection. Speech auto-submits when Flux
              detects you've finished speaking.
            </p>
          {/if}
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Account</h3>
          <p class="system-card-caption">
            Session and authentication settings.
          </p>
        </div>
      </header>

      <div class="system-card-body">
        <div class="account-actions">
          <a
            href="/cdn-cgi/access/logout"
            class="btn btn-danger"
            title="End your session and require re-authentication"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
            Logout
          </a>
          <p class="speech-hint">
            Ends your Cloudflare Access session. You'll need to re-authenticate
            with your email.
          </p>
        </div>
      </div>
    </article>

    <footer slot="footer" class="model-settings-footer system-settings-footer">
      {#if $systemPrompt.saveError}
        <p class="status error">Resolve the errors above before closing.</p>
      {:else if speechSaveError}
        <p class="status error">{speechSaveError}</p>
      {:else if serverSttError}
        <p class="status error">{serverSttError}</p>
      {:else if $systemPrompt.saving || speechSaving || serverSttSaving}
        <p class="status">Saving changes…</p>
      {:else if $systemPrompt.dirty || speechDirty || serverSttDirty}
        <p class="status">Pending changes; closing this modal will save.</p>
      {:else}
        <p class="status">Changes save when you close this modal.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
