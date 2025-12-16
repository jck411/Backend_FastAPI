<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import {
    getDefaultKioskSttSettings,
    kioskSettingsStore,
    type KioskSttSettings,
  } from "../../stores/kioskSettings";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./model-settings/model-settings-styles.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  let draft: KioskSttSettings = getDefaultKioskSttSettings();
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
      const settings = await kioskSettingsStore.load();
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
      const saved = await kioskSettingsStore.save(draft);
      draft = { ...saved };
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
      const settings = await kioskSettingsStore.reset();
      draft = { ...settings };
      dirty = false;
      statusMessage = null;
    } catch (error) {
      statusMessage = "Failed to reset settings";
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
    labelledBy="kiosk-settings-title"
    closeLabel="Close kiosk settings"
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="kiosk-settings-title">Kiosk settings</h2>
      <p class="model-settings-subtitle">
        Configure the voice assistant kiosk.
      </p>
    </svelte:fragment>

    <button
      slot="actions"
      type="button"
      class="btn btn-ghost btn-small"
      on:click={handleReset}
      disabled={saving || loading}
    >
      Reset to defaults
    </button>

    {#if loading}
      <p class="status">Loading settings…</p>
    {:else}
      <div class="settings-stack" aria-live="polite">
        <!-- STT Settings Section -->
        <div class="setting reasoning">
          <div class="setting-header">
            <span class="setting-label">Speech Recognition</span>
            <span class="setting-hint"
              >Deepgram Flux end-of-turn detection settings.</span
            >
          </div>

          <div class="reasoning-controls">
            <!-- EOT Threshold -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Confidence level (0.5-0.9) required before the system considers you've finished speaking. Lower = faster response but may cut you off. Higher = waits longer to be sure you're done."
                    >EOT Threshold</span
                  >
                  <span class="range-value"
                    >{draft.eot_threshold.toFixed(2)}</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="0.5"
                  max="0.9"
                  step="0.05"
                  value={draft.eot_threshold}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.eot_threshold,
                    0.5,
                    0.9,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      eot_threshold: parseFloat(
                        (e.target as HTMLInputElement).value,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>0.5 (fast)</span>
                  <span>0.9 (reliable)</span>
                </div>
              </div>
            </div>

            <!-- EOT Timeout -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Maximum time (ms) to wait after speech before forcing end-of-turn, regardless of confidence. Shorter = faster response. Longer = allows for natural pauses."
                    >EOT Timeout</span
                  >
                  <span class="range-value">{draft.eot_timeout_ms}ms</span>
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="500"
                  max="10000"
                  step="250"
                  value={draft.eot_timeout_ms}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.eot_timeout_ms,
                    500,
                    10000,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      eot_timeout_ms: parseInt(
                        (e.target as HTMLInputElement).value,
                        10,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>500ms</span>
                  <span>10s</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Advanced Settings Section -->
        <div class="setting">
          <div class="setting-header">
            <span class="setting-label">Advanced</span>
            <span class="setting-hint">Optional fine-tuning options.</span>
          </div>

          <label
            class="setting-boolean"
            title="When enabled, the system can speculatively start processing before you fully finish speaking. This reduces latency but may cause 'false starts' if you pause mid-sentence."
          >
            <input
              type="checkbox"
              checked={draft.eager_eot_threshold !== null}
              disabled={saving}
              on:change={(e) => {
                const checked = (e.target as HTMLInputElement).checked;
                draft = { ...draft, eager_eot_threshold: checked ? 0.5 : null };
                markDirty();
              }}
            />
            <span>Enable eager end-of-turn</span>
          </label>

          {#if draft.eager_eot_threshold !== null}
            <div class="setting-range" style="margin-top: 0.75rem;">
              <div class="setting-range-header">
                <span
                  class="setting-label"
                  title="Confidence level for triggering early processing. Lower = starts processing sooner (more false starts). Higher = waits longer before speculating."
                  >Eager EOT Threshold</span
                >
                <span class="range-value"
                  >{draft.eager_eot_threshold?.toFixed(2) ?? "—"}</span
                >
              </div>
              <input
                type="range"
                class="range-input"
                min="0.3"
                max="0.9"
                step="0.05"
                value={draft.eager_eot_threshold ?? 0.5}
                disabled={saving}
                style="--slider-fill: {getSliderFill(
                  draft.eager_eot_threshold ?? 0.5,
                  0.3,
                  0.9,
                )}"
                on:input={(e) => {
                  draft = {
                    ...draft,
                    eager_eot_threshold: parseFloat(
                      (e.target as HTMLInputElement).value,
                    ),
                  };
                  markDirty();
                }}
              />
              <div class="range-extents">
                <span>0.3 (eager)</span>
                <span>0.9 (conservative)</span>
              </div>
            </div>
          {/if}
        </div>

        <!-- Keyterms Section -->
        <div class="setting">
          <div class="setting-header">
            <span
              class="setting-label"
              title="Words or phrases the speech recognition should pay extra attention to. Useful for device names, product terms, or commands specific to your home automation setup."
              >Keyterms</span
            >
            <span class="setting-hint"
              >Words to boost recognition (one per line, up to 100).</span
            >
          </div>
          <textarea
            class="keyterms-input"
            rows="3"
            disabled={saving}
            placeholder="lights&#10;thermostat&#10;turn on"
            on:input={(e) => {
              const text = (e.target as HTMLTextAreaElement).value;
              const terms = text
                .split("\n")
                .map((t) => t.trim())
                .filter((t) => t.length > 0)
                .slice(0, 100);
              draft = { ...draft, keyterms: terms };
              markDirty();
            }}>{draft.keyterms.join("\n")}</textarea
          >
        </div>

        <!-- Placeholder for future sections -->
        <!-- TODO: Model Selection -->
        <!-- TODO: System Prompt -->
        <!-- TODO: MCP Server Selection -->
      </div>
    {/if}

    <footer slot="footer" class="model-settings-footer">
      {#if statusMessage}
        <span class="status error">{statusMessage}</span>
      {:else if saving}
        <span class="status">Saving changes…</span>
      {:else if dirty}
        <span class="status"
          >Pending changes; closing this modal will save.</span
        >
      {:else}
        <span class="status">Changes save when you close this modal.</span>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}

<style>
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
</style>
