<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import {
    DEEPGRAM_MODEL_OPTIONS,
    SPEECH_TIMING_PRESETS,
    type SpeechSettings,
    type SpeechTimingPresetKey,
    getDefaultSpeechSettings,
    speechSettingsStore,
  } from '../../stores/speechSettings';
  import './model-settings/model-settings-styles.css';
  import './speech-settings.css';

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  let dialogEl: HTMLElement | null = null;
  let draft: SpeechSettings = initializeDraft();
  let dirty = false;
  let saving = false;
  let statusMessage: string | null = null;
  let statusVariant: 'success' | 'error' | 'pending' | 'info' | null = null;
  let wasOpen = false;
  let closing = false;

  $: if (open && !wasOpen) {
    draft = initializeDraft();
    dirty = false;
    saving = false;
    statusMessage = 'Changes save when you close this modal.';
    statusVariant = 'info' as const;
    wasOpen = true;
    if (dialogEl) {
      dialogEl.focus();
    }
  } else if (!open && wasOpen) {
    wasOpen = false;
    if (dirty && !saving) {
      void flushSave();
    }
  }

  function initializeDraft(): SpeechSettings {
    const current = speechSettingsStore.current ?? getDefaultSpeechSettings();
    return {
      ...current,
      stt: { ...current.stt },
    };
  }

  function closeModal(): void {
    if (closing || saving) {
      return;
    }
    closing = true;
    void (async () => {
      const success = await flushSave();
      if (success) {
        dispatch('close');
      }
      closing = false;
    })();
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
      void closeModal();
    }
  }

  function markDirty(message: string | null = null, variant: 'success' | 'error' | 'pending' | null = 'pending'): void {
    dirty = true;
    statusMessage = message;
    statusVariant = variant ?? 'pending';
  }

  function updateStt<K extends keyof SpeechSettings['stt']>(key: K, value: SpeechSettings['stt'][K]): void {
    draft = {
      ...draft,
      stt: {
        ...draft.stt,
        [key]: value,
      },
    };
    markDirty();
  }

  function handleNumberInput(
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

  function applyPreset(key: SpeechTimingPresetKey): void {
    const preset = SPEECH_TIMING_PRESETS[key];
    draft = {
      ...draft,
      stt: {
        ...draft.stt,
        utteranceEndMs: preset.stt.utteranceEndMs,
        endpointing: preset.stt.endpointing,
        autoSubmitDelayMs: preset.stt.autoSubmitDelayMs,
      },
    };
    markDirty(`${preset.label} preset applied; closing will save.`, 'pending');
  }

  async function flushSave(): Promise<boolean> {
    if (!dirty) {
      return true;
    }

    saving = true;
    statusMessage = 'Saving changes…';
    statusVariant = 'pending';

    try {
      const saved = speechSettingsStore.save(draft);
      draft = {
        ...saved,
        stt: { ...saved.stt },
      };
      dirty = false;
      statusMessage = 'Saved';
      statusVariant = 'success';
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save speech settings.';
      statusMessage = message;
      statusVariant = 'error';
      return false;
    } finally {
      saving = false;
    }
  }

  function handleReset(): void {
    draft = getDefaultSpeechSettings();
    dirty = true;
    statusMessage = 'Defaults restored; closing will save.';
    statusVariant = 'pending';
  }

</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="model-settings-layer">
    <button
      type="button"
      class="model-settings-backdrop"
      aria-label="Close speech settings"
      on:click={handleBackdrop}
    ></button>
    <div
      class="model-settings-modal speech-settings-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="speech-settings-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="model-settings-header">
        <div class="model-settings-heading">
          <h2 id="speech-settings-title">Speech settings</h2>
          <p class="model-settings-subtitle">Configure Deepgram speech-to-text dictation settings.</p>
        </div>
        <div class="model-settings-actions">
          <button type="button" class="ghost small" on:click={handleReset} disabled={saving}>
            Reset to defaults
          </button>
          <button type="button" class="modal-close" on:click={() => void closeModal()} aria-label="Close">
            Close
          </button>
        </div>
      </header>

      <section class="model-settings-body speech-settings-body">
        <div class="speech-card">
          <div class="speech-card-header">
            <h3>Deepgram model</h3>
            <p>Choose the speech-to-text engine and helper features.</p>
          </div>

          <div class="model-presets-row">
            <div class="speech-field">
              <span class="field-label">Model</span>
              <select
                value={draft.stt.model}
                on:change={(event) => updateStt('model', (event.target as HTMLSelectElement).value)}
              >
                {#each DEEPGRAM_MODEL_OPTIONS as option}
                  <option value={option.value}>{option.label}</option>
                {/each}
              </select>
            </div>
            <div class="speech-field presets-field">
              <span class="field-label">Speech timing presets</span>
              <div class="speech-presets" aria-label="Timing presets">
                <button type="button" on:click={() => applyPreset('fast')}>Fast</button>
                <button type="button" on:click={() => applyPreset('normal')}>Normal</button>
                <button type="button" on:click={() => applyPreset('slow')}>Slow</button>
              </div>
            </div>
          </div>

          <div class="toggle-grid">
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.interimResults}
                on:change={(event) => updateStt('interimResults', (event.target as HTMLInputElement).checked)}
              />
              <span>Interim transcripts</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.vadEvents}
                on:change={(event) => updateStt('vadEvents', (event.target as HTMLInputElement).checked)}
              />
              <span>VAD events</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.smartFormat}
                on:change={(event) => updateStt('smartFormat', (event.target as HTMLInputElement).checked)}
              />
              <span>Smart formatting</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.punctuate}
                on:change={(event) => updateStt('punctuate', (event.target as HTMLInputElement).checked)}
              />
              <span>Punctuation</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.numerals}
                on:change={(event) => updateStt('numerals', (event.target as HTMLInputElement).checked)}
              />
              <span>Numerals</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.fillerWords}
                on:change={(event) => updateStt('fillerWords', (event.target as HTMLInputElement).checked)}
              />
              <span>Keep filler words</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={draft.stt.profanityFilter}
                on:change={(event) => updateStt('profanityFilter', (event.target as HTMLInputElement).checked)}
              />
              <span>Profanity filter</span>
            </label>
          </div>
        </div>

        <div class="speech-card">
          <div class="speech-card-header">
            <h3>Timing & auto-submit</h3>
            <p>Tune silence detection and message submission.</p>
          </div>

          <div class="timing-grid">
            <div class="speech-field">
              <span class="field-label">Endpointing window (ms)</span>
              <input
                type="number"
                min="300"
                max="5000"
                step="50"
                value={draft.stt.endpointing}
                on:change={(event) => handleNumberInput(event, (value) => updateStt('endpointing', value))}
              />
              <p class="speech-hint">How long Deepgram waits after silence before finalizing the transcript.</p>
            </div>
            <div class="speech-field">
              <span class="field-label">Utterance gap (ms)</span>
              <input
                type="number"
                min="500"
                max="5000"
                step="50"
                value={draft.stt.utteranceEndMs}
                on:change={(event) => handleNumberInput(event, (value) => updateStt('utteranceEndMs', value))}
              />
              <p class="speech-hint">Silence between words before Deepgram starts a new interim segment.</p>
            </div>
          </div>

          <div class="auto-submit-block">
            <div class="auto-submit-row">
              <label class="inline-checkbox">
                <input
                  type="checkbox"
                  checked={draft.stt.autoSubmit}
                  on:change={(event) => updateStt('autoSubmit', (event.target as HTMLInputElement).checked)}
                />
                <span class="field-label">Auto-submit</span>
              </label>
              <p class="speech-hint">Send automatically when speech ends. Delay waits after endpointing.</p>
            </div>
            <div class="delay-inline">
              <label class="delay-label" for="auto-submit-delay-input">Delay (ms)</label>
              <input
                id="auto-submit-delay-input"
                type="number"
                min="0"
                max="20000"
                step="50"
                value={draft.stt.autoSubmitDelayMs}
                disabled={!draft.stt.autoSubmit}
                on:change={(event) => handleNumberInput(event, (value) => updateStt('autoSubmitDelayMs', value))}
              />
            </div>
          </div>
        </div>

        <footer class="speech-footer">
          {#if statusVariant === 'error'}
            <p class="status" data-variant="error" aria-live="assertive">{statusMessage}</p>
          {:else if saving}
            <p class="status" data-variant="pending" aria-live="polite">Saving changes…</p>
          {:else if dirty}
            <p class="status" data-variant="pending" aria-live="polite">
              {statusMessage ?? 'Pending changes; closing this modal will save.'}
            </p>
          {:else}
            <p class="status" data-variant={statusVariant ?? 'info'} aria-live="polite">
              {statusMessage ?? 'Changes save when you close this modal.'}
            </p>
          {/if}
        </footer>
      </section>
    </div>
  </div>
{/if}
