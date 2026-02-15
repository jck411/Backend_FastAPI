<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import {
    SPEECH_TIMING_PRESETS,
    type SpeechSettings,
    type SpeechTimingPresetKey,
    getDefaultSpeechSettings,
    speechSettingsStore,
  } from "../../stores/speechSettings";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import {
    applyModalVisibility,
    closeModalWithFlush,
  } from "./model-settings/modalLifecycle";
  import "./speech-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  let draft: SpeechSettings = initializeDraft();
  let dirty = false;
  let saving = false;
  let statusMessage: string | null = null;
  let statusVariant: "success" | "error" | "pending" | "info" | null = null;
  let wasOpen = false;
  let closing = false;

  $: wasOpen = applyModalVisibility({
    open,
    wasOpen,
    onOpened: () => {
      draft = initializeDraft();
      dirty = false;
      saving = false;
      statusMessage = "Changes save when you close this modal.";
      statusVariant = "info";
    },
    onClosed: () => {
      if (dirty && !saving) {
        void flushSave();
      }
    },
  });

  function initializeDraft(): SpeechSettings {
    const current = speechSettingsStore.current ?? getDefaultSpeechSettings();
    return {
      ...current,
      stt: { ...current.stt },
    };
  }

  function closeModal(): void {
    void closeModalWithFlush({
      closing,
      saving,
      setClosing: (value) => {
        closing = value;
      },
      flushSave,
      onClosed: () => {
        dispatch("close");
      },
    });
  }

  function markDirty(
    message: string | null = null,
    variant: "success" | "error" | "pending" | null = "pending",
  ): void {
    dirty = true;
    statusMessage = message;
    statusVariant = variant ?? "pending";
  }

  function updateStt<K extends keyof SpeechSettings["stt"]>(
    key: K,
    value: SpeechSettings["stt"][K],
  ): void {
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
        autoSubmitDelayMs: preset.autoSubmitDelayMs,
      },
    };
    markDirty(`${preset.label} preset applied; closing will save.`, "pending");
  }

  async function flushSave(): Promise<boolean> {
    if (!dirty) {
      return true;
    }

    saving = true;
    statusMessage = "Saving changes…";
    statusVariant = "pending";

    try {
      const saved = speechSettingsStore.save(draft);
      draft = {
        ...saved,
        stt: { ...saved.stt },
      };
      dirty = false;
      statusMessage = "Saved";
      statusVariant = "success";
      return true;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to save speech settings.";
      statusMessage = message;
      statusVariant = "error";
      return false;
    } finally {
      saving = false;
    }
  }

  function handleReset(): void {
    draft = getDefaultSpeechSettings();
    dirty = true;
    statusMessage = "Defaults restored; closing will save.";
    statusVariant = "pending";
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="speech-settings-title"
    modalClass="speech-settings-modal"
    bodyClass="speech-settings-body"
    closeLabel="Close speech settings"
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="speech-settings-title">Speech settings</h2>
      <p class="model-settings-subtitle">Configure speech-to-text behavior.</p>
    </svelte:fragment>

    <button
      slot="actions"
      type="button"
      class="btn btn-ghost btn-small"
      on:click={handleReset}
      disabled={saving}
    >
      Reset to defaults
    </button>

    <div class="speech-card">
      <div class="speech-card-header">
        <h3>Auto-submit timing</h3>
        <p>Control when your speech is automatically sent.</p>
      </div>

      <div class="auto-submit-block">
        <div class="auto-submit-row">
          <label class="inline-checkbox">
            <input
              class="input-control"
              type="checkbox"
              checked={draft.stt.autoSubmit}
              on:change={(event) =>
                updateStt(
                  "autoSubmit",
                  (event.target as HTMLInputElement).checked,
                )}
            />
            <span class="field-label">Auto-submit</span>
          </label>
          <p class="speech-hint">Automatically send when you stop speaking.</p>
        </div>

        <div class="speech-field presets-field">
          <span class="field-label">Timing presets</span>
          <div class="speech-presets" aria-label="Timing presets">
            <button
              class="btn btn-soft btn-small"
              type="button"
              on:click={() => applyPreset("fast")}>Fast (0ms)</button
            >
            <button
              class="btn btn-soft btn-small"
              type="button"
              on:click={() => applyPreset("normal")}>Normal (300ms)</button
            >
            <button
              class="btn btn-soft btn-small"
              type="button"
              on:click={() => applyPreset("slow")}>Slow (800ms)</button
            >
          </div>
        </div>

        <div class="delay-inline">
          <label class="delay-label" for="auto-submit-delay-input"
            >Delay before submit (ms)</label
          >
          <input
            id="auto-submit-delay-input"
            class="input-control"
            type="number"
            min="0"
            max="10000"
            step="50"
            value={draft.stt.autoSubmitDelayMs}
            disabled={!draft.stt.autoSubmit}
            on:change={(event) =>
              handleNumberInput(event, (value) =>
                updateStt("autoSubmitDelayMs", value),
              )}
          />
          <p class="speech-hint">
            Wait this long after you stop speaking before sending.
          </p>
        </div>
      </div>
    </div>

    <footer slot="footer" class="model-settings-footer">
      {#if statusVariant === "error"}
        <p class="status" data-variant="error" aria-live="assertive">
          {statusMessage}
        </p>
      {:else if saving}
        <p class="status" data-variant="pending" aria-live="polite">
          Saving changes…
        </p>
      {:else if dirty}
        <p class="status" data-variant="pending" aria-live="polite">
          {statusMessage ?? "Pending changes; closing this modal will save."}
        </p>
      {:else}
        <p
          class="status"
          data-variant={statusVariant ?? "info"}
          aria-live="polite"
        >
          {statusMessage ?? "Changes save when you close this modal."}
        </p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
