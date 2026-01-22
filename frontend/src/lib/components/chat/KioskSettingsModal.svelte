<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import {
    activateKioskPreset,
    fetchKioskPresets,
    fetchTtsVoices,
    updateKioskPreset,
    type KioskPresets,
    type TtsVoice,
  } from "../../api/kiosk";
  import {
    getDefaultKioskSttSettings,
    kioskSettingsStore,
    type KioskSettings,
  } from "../../stores/kioskSettings";
  import { modelStore } from "../../stores/models";
  import { autoSize } from "./autoSize";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./model-settings/model-settings-styles.css";
  import "./system-settings.css";

  const { filtered } = modelStore;

  // Available TTS voices (loaded from API based on provider)
  let ttsVoices: TtsVoice[] = [];

  // Kiosk presets
  let presets: KioskPresets | null = null;
  let activatingPreset = false;

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  let draft: KioskSettings = getDefaultKioskSttSettings();
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
      const [settings, presetsData] = await Promise.all([
        kioskSettingsStore.load(),
        fetchKioskPresets(),
        modelStore.loadModels(),
      ]);
      draft = { ...settings };
      // Always load OpenAI voices
      ttsVoices = await fetchTtsVoices("openai");
      presets = presetsData;
    } catch (error) {
      statusMessage = "Failed to load settings";
    } finally {
      loading = false;
    }
  }

  async function handlePresetClick(index: number): Promise<void> {
    if (activatingPreset) return;
    activatingPreset = true;
    try {
      presets = await activateKioskPreset(index);
      // Reload settings to get updated LLM values
      const settings = await kioskSettingsStore.load();
      draft = { ...settings };
      dirty = false;
    } catch (error) {
      statusMessage = "Failed to activate preset";
    } finally {
      activatingPreset = false;
    }
  }

  async function handleSavePreset(): Promise<void> {
    if (!presets || activatingPreset) return;
    activatingPreset = true;
    try {
      const activeIndex = presets.active_index;
      const currentPreset = presets.presets[activeIndex];
      const updatedPreset = {
        name: currentPreset.name,
        // LLM settings
        model: draft.llm_model,
        system_prompt: draft.system_prompt ?? "",
        temperature: draft.temperature,
        max_tokens: draft.max_tokens,
        // STT settings
        eot_threshold: draft.eot_threshold,
        eot_timeout_ms: draft.eot_timeout_ms,
        keyterms: draft.keyterms,
        // TTS settings
        tts_enabled: draft.enabled,
        tts_voice: draft.voice,
        tts_model: draft.model,
        tts_sample_rate: draft.sample_rate,
      };
      presets = await updateKioskPreset(activeIndex, updatedPreset);
      statusMessage = `Saved to "${currentPreset.name}"`;
      setTimeout(() => {
        if (statusMessage?.startsWith("Saved")) statusMessage = null;
      }, 2000);
    } catch (error) {
      statusMessage = "Failed to save preset";
    } finally {
      activatingPreset = false;
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
        <!-- LLM Settings Section -->
        <div class="setting reasoning">
          <div class="setting-header">
            <span class="setting-label">Language Model</span>
            <span class="setting-hint"
              >Configure the AI model and behavior.</span
            >
          </div>

          <div class="reasoning-controls">
            <!-- Row 1: Model + Presets -->
            <div class="model-presets-row">
              <!-- Model Selection -->
              <div class="setting-select model-select-compact">
                <label
                  class="setting-label"
                  for="llm-model"
                  title="Select the language model for generating responses."
                  >Model</label
                >
                <select
                  id="llm-model"
                  class="select-input"
                  value={draft.llm_model}
                  disabled={saving}
                  on:change={(e) => {
                    draft = {
                      ...draft,
                      llm_model: (e.target as HTMLSelectElement).value,
                    };
                    markDirty();
                  }}
                >
                  {#each $filtered as model (model.id)}
                    <option value={model.id}>{model.name ?? model.id}</option>
                  {/each}
                </select>
              </div>

              <!-- Presets -->
              {#if presets}
                <div class="presets-container">
                  <label class="setting-label" for="preset-select">Preset</label
                  >
                  <div class="preset-select-row">
                    <select
                      id="preset-select"
                      class="select-input"
                      value={presets.active_index}
                      disabled={saving || activatingPreset}
                      on:change={(e) =>
                        handlePresetClick(
                          parseInt((e.target as HTMLSelectElement).value, 10),
                        )}
                    >
                      {#each presets.presets as preset, index (index)}
                        <option value={index}>{preset.name}</option>
                      {/each}
                    </select>
                    <button
                      type="button"
                      class="btn btn-ghost btn-small"
                      disabled={saving || activatingPreset}
                      title="Save current settings to the selected preset"
                      on:click={handleSavePreset}
                    >
                      💾 Save
                    </button>
                  </div>
                </div>
              {/if}
            </div>

            <!-- Row 2: System Prompt (full width) -->
            <div class="system-prompt-row">
              <label
                class="setting-label"
                for="system-prompt"
                title="Instructions that define how the assistant behaves."
                >System Prompt</label
              >
              <textarea
                id="system-prompt"
                class="keyterms-input system-prompt"
                rows="4"
                disabled={saving}
                placeholder="You are a helpful voice assistant..."
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

            <!-- Temperature -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Controls randomness in responses. Lower = more focused, higher = more creative. Note: Some models don't support this parameter."
                    >Temperature</span
                  >
                  <span class="range-value">{draft.temperature.toFixed(1)}</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="0"
                  max="2"
                  step="0.1"
                  value={draft.temperature}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.temperature,
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

            <!-- Max Tokens -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Maximum length of responses in tokens. Keep low for voice interactions."
                    >Max Tokens</span
                  >
                  <span class="range-value">{draft.max_tokens}</span>
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="50"
                  max="2000"
                  step="50"
                  value={draft.max_tokens}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.max_tokens,
                    50,
                    2000,
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
                  <span>50 (short)</span>
                  <span>2000 (long)</span>
                </div>
              </div>
            </div>
          </div>
        </div>

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

            <!-- Keyterms -->
            <div class="reasoning-field" style="grid-column: 1 / -1;">
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

        <!-- Display Settings Section -->
        <div class="setting reasoning">
          <div class="setting-header">
            <span class="setting-label">Display</span>
            <span class="setting-hint">Kiosk screen behavior settings.</span>
          </div>

          <div class="reasoning-controls">
            <!-- Conversation Mode Toggle - full width at top -->
            <label
              class="setting-boolean"
              title="When enabled, the microphone re-opens after the assistant speaks, allowing continuous conversation without needing the wake word."
              style="grid-column: 1 / -1;"
            >
              <input
                type="checkbox"
                checked={draft.conversation_mode}
                disabled={saving}
                on:change={(e) => {
                  draft = {
                    ...draft,
                    conversation_mode: (e.target as HTMLInputElement).checked,
                  };
                  markDirty();
                }}
              />
              <span>Continuous conversation mode</span>
            </label>

            <!-- Return to Clock slider -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="How long (seconds) to wait on the transcription screen after going IDLE before returning to the clock screen."
                    >Return to Clock</span
                  >
                  <span class="range-value"
                    >{(draft.idle_return_delay_ms / 1000).toFixed(0)}s</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="1000"
                  max="60000"
                  step="1000"
                  value={draft.idle_return_delay_ms}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.idle_return_delay_ms,
                    1000,
                    60000,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      idle_return_delay_ms: parseInt(
                        (e.target as HTMLInputElement).value,
                        10,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>1s</span>
                  <span>60s</span>
                </div>
              </div>
            </div>

            <!-- Conversation Timeout slider -->
            <div
              class="reasoning-field"
              class:disabled-field={!draft.conversation_mode}
            >
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="How long (seconds) to wait for speech before ending the conversation session and returning to the clock."
                    >Conversation Timeout</span
                  >
                  <span class="range-value"
                    >{draft.conversation_timeout_seconds.toFixed(0)}s</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="1"
                  max="60"
                  step="1"
                  value={draft.conversation_timeout_seconds}
                  disabled={saving || !draft.conversation_mode}
                  style="--slider-fill: {getSliderFill(
                    draft.conversation_timeout_seconds,
                    1,
                    60,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      conversation_timeout_seconds: parseFloat(
                        (e.target as HTMLInputElement).value,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>1s</span>
                  <span>60s</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- TTS Settings Section -->
        <div class="setting reasoning">
          <div class="setting-header">
            <span class="setting-label">Text-to-Speech</span>
            <span class="setting-hint"
              >Voice synthesis settings for assistant responses.</span
            >
          </div>

          <div class="reasoning-controls">
            <!-- TTS Enabled Toggle -->
            <label
              class="setting-boolean"
              title="Enable or disable audio playback of assistant responses."
            >
              <input
                type="checkbox"
                checked={draft.enabled}
                disabled={saving}
                on:change={(e) => {
                  draft = {
                    ...draft,
                    enabled: (e.target as HTMLInputElement).checked,
                  };
                  markDirty();
                }}
              />
              <span>Enable TTS</span>
            </label>

            {#if draft.enabled}
              <!-- Voice Selection (OpenAI) -->
              <div class="reasoning-field">
                <div class="setting-select">
                  <label
                    class="setting-label"
                    for="tts-voice"
                    title="Select the OpenAI voice for text-to-speech synthesis."
                    >Voice</label
                  >
                  <select
                    id="tts-voice"
                    class="select-input"
                    value={draft.voice}
                    disabled={saving}
                    on:change={(e) => {
                      draft = {
                        ...draft,
                        voice: (e.target as HTMLSelectElement).value,
                      };
                      markDirty();
                    }}
                  >
                    {#each ttsVoices as voice}
                      <option value={voice.id}>{voice.name}</option>
                    {/each}
                  </select>
                </div>
              </div>

              <!-- Model Selection (OpenAI) -->
              <div class="reasoning-field">
                <div class="setting-select">
                  <label
                    class="setting-label"
                    for="tts-model"
                    title="Select the OpenAI TTS model.">Model</label
                  >
                  <select
                    id="tts-model"
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
                    <option value="tts-1">tts-1 (faster)</option>
                    <option value="tts-1-hd">tts-1-hd (higher quality)</option>
                  </select>
                </div>
              </div>

              <!-- Response Format -->
              <div class="reasoning-field">
                <div class="setting-select">
                  <label
                    class="setting-label"
                    for="tts-response-format"
                    title="Audio format returned by the TTS service."
                    >Response format</label
                  >
                  <select
                    id="tts-response-format"
                    class="select-input"
                    value={draft.response_format}
                    disabled={saving}
                    on:change={(e) => {
                      draft = {
                        ...draft,
                        response_format: (e.target as HTMLSelectElement).value,
                      };
                      markDirty();
                    }}
                  >
                    <option value="pcm">pcm</option>
                    <option value="mp3">mp3</option>
                    <option value="opus">opus</option>
                    <option value="aac">aac</option>
                    <option value="flac">flac</option>
                    <option value="wav">wav</option>
                  </select>
                </div>
              </div>

              <!-- Speed Slider -->
              <div class="reasoning-field">
                <div class="setting-range">
                  <div class="setting-range-header">
                    <span
                      class="setting-label"
                      title="Speech speed multiplier. 1.0 is normal speed."
                      >Speed</span
                    >
                    <span class="range-value">{draft.speed.toFixed(1)}x</span>
                  </div>
                  <input
                    type="range"
                    class="range-input"
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={draft.speed}
                    disabled={saving}
                    style="--slider-fill: {getSliderFill(
                      draft.speed,
                      0.5,
                      2.0,
                    )}"
                    on:input={(e) => {
                      draft = {
                        ...draft,
                        speed: parseFloat((e.target as HTMLInputElement).value),
                      };
                      markDirty();
                    }}
                  />
                  <div class="range-extents">
                    <span>0.5x (slow)</span>
                    <span>2x (fast)</span>
                  </div>
                </div>
              </div>

              <!-- Sample Rate -->
              <div class="reasoning-field">
                <div class="setting-select">
                  <label
                    class="setting-label"
                    for="tts-sample-rate"
                    title="Sample rate in Hz for TTS audio."
                    >Sample rate (Hz)</label
                  >
                  <input
                    id="tts-sample-rate"
                    class="select-input"
                    type="number"
                    min="8000"
                    max="48000"
                    step="1000"
                    value={draft.sample_rate}
                    disabled={saving}
                    on:input={(e) => {
                      const next = parseInt(
                        (e.target as HTMLInputElement).value,
                        10,
                      );
                      if (!Number.isFinite(next)) return;
                      draft = {
                        ...draft,
                        sample_rate: Math.max(8000, Math.min(48000, next)),
                      };
                      markDirty();
                    }}
                  />
                </div>
              </div>

              <!-- Stream Chunk Bytes -->
              <div class="reasoning-field">
                <div class="setting-select">
                  <label
                    class="setting-label"
                    for="tts-stream-chunk-bytes"
                    title="Chunk size (bytes) when streaming TTS audio."
                    >Stream chunk bytes</label
                  >
                  <input
                    id="tts-stream-chunk-bytes"
                    class="select-input"
                    type="number"
                    min="512"
                    max="65536"
                    step="256"
                    value={draft.stream_chunk_bytes}
                    disabled={saving}
                    on:input={(e) => {
                      const next = parseInt(
                        (e.target as HTMLInputElement).value,
                        10,
                      );
                      if (!Number.isFinite(next)) return;
                      draft = {
                        ...draft,
                        stream_chunk_bytes: Math.max(
                          512,
                          Math.min(65536, next),
                        ),
                      };
                      markDirty();
                    }}
                  />
                </div>
              </div>

              <!-- Segmentation Toggle -->
              <label
                class="setting-boolean"
                title="Split text at delimiters to start audio sooner."
                style="grid-column: 1 / -1;"
              >
                <input
                  type="checkbox"
                  checked={draft.use_segmentation}
                  disabled={saving}
                  on:change={(e) => {
                    draft = {
                      ...draft,
                      use_segmentation: (e.target as HTMLInputElement).checked,
                    };
                    markDirty();
                  }}
                />
                <span>Enable text segmentation</span>
              </label>

              <div
                class="reasoning-field"
                class:disabled-field={!draft.use_segmentation}
                style="grid-column: 1 / -1;"
              >
                <div class="setting-header">
                  <span
                    class="setting-label"
                    title="Minimum characters to accumulate before the first segmented phrase is emitted."
                    >Minimum first phrase length</span
                  >
                  <span class="setting-hint"
                    >Set a floor so the first spoken chunk feels complete.</span
                  >
                </div>
                <input
                  class="select-input"
                  type="number"
                  min="0"
                  max="500"
                  step="1"
                  value={draft.first_phrase_min_chars}
                  disabled={saving || !draft.use_segmentation}
                  on:input={(e) => {
                    const next = parseInt(
                      (e.target as HTMLInputElement).value,
                      10,
                    );
                    if (!Number.isFinite(next)) return;
                    draft = {
                      ...draft,
                      first_phrase_min_chars: Math.max(0, Math.min(500, next)),
                    };
                    markDirty();
                  }}
                />
              </div>

              <label
                class="setting-boolean"
                title="Log when segmentation is waiting for a delimiter after the minimum is reached."
                class:disabled-field={!draft.use_segmentation}
                style="grid-column: 1 / -1;"
              >
                <input
                  type="checkbox"
                  checked={draft.segmentation_logging_enabled}
                  disabled={saving || !draft.use_segmentation}
                  on:change={(e) => {
                    draft = {
                      ...draft,
                      segmentation_logging_enabled: (
                        e.target as HTMLInputElement
                      ).checked,
                    };
                    markDirty();
                  }}
                />
                <span>Log segmentation boundary decisions</span>
              </label>

              <!-- Delimiters -->
              <div
                class="reasoning-field"
                class:disabled-field={!draft.use_segmentation}
                style="grid-column: 1 / -1;"
              >
                <div class="setting-header">
                  <span
                    class="setting-label"
                    title="One delimiter per line. Use \\n for newline."
                    >Delimiters</span
                  >
                  <span class="setting-hint"
                    >Whitespace matters; each line becomes a delimiter.</span
                  >
                </div>
                <textarea
                  class="keyterms-input"
                  rows="4"
                  disabled={saving || !draft.use_segmentation}
                  placeholder="\\n&#10;. &#10;? &#10;! "
                  on:input={(e) => {
                    const text = (e.target as HTMLTextAreaElement).value;
                    const lines = text
                      .split("\n")
                      .map((line) => line.replace(/\r/g, ""))
                      .map((line) => (line === "\\n" ? "\n" : line))
                      .filter((line) => line.trim().length > 0);
                    draft = { ...draft, delimiters: lines };
                    markDirty();
                  }}
                  >{draft.delimiters
                    .map((delimiter) =>
                      delimiter === "\n" ? "\\n" : delimiter,
                    )
                    .join("\n")}</textarea
                >
              </div>
            {/if}
          </div>
        </div>

        <!-- Audio Buffer Settings Section -->
        <div class="setting reasoning">
          <div class="setting-header">
            <span
              class="setting-label"
              title="Controls how audio chunks are queued before playback. Larger buffers reduce stuttering on slow devices but add latency. Smaller buffers feel more responsive but may cause gaps if the network or device can't keep up."
              >Audio Buffering</span
            >
            <span class="setting-hint"
              >Buffer timing for smoother playback on slower devices.</span
            >
          </div>

          <div class="reasoning-controls">
            <!-- Initial Buffer Slider -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Minimum audio (seconds) to buffer before playback starts."
                    >Initial Buffer</span
                  >
                  <span class="range-value"
                    >{draft.initial_buffer_sec.toFixed(2)}s</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="0.05"
                  max="2.0"
                  step="0.05"
                  value={draft.initial_buffer_sec}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.initial_buffer_sec,
                    0.05,
                    2.0,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      initial_buffer_sec: parseFloat(
                        (e.target as HTMLInputElement).value,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>0.05s (fast start)</span>
                  <span>2.0s (smooth)</span>
                </div>
              </div>
            </div>

            <!-- Max Ahead Slider -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Maximum audio (seconds) to schedule ahead of current time."
                    >Max Ahead</span
                  >
                  <span class="range-value"
                    >{draft.max_ahead_sec.toFixed(1)}s</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="0.3"
                  max="5.0"
                  step="0.1"
                  value={draft.max_ahead_sec}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.max_ahead_sec,
                    0.3,
                    5.0,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      max_ahead_sec: parseFloat(
                        (e.target as HTMLInputElement).value,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>0.3s (tight)</span>
                  <span>5.0s (buffered)</span>
                </div>
              </div>
            </div>

            <!-- Min Chunk Slider -->
            <div class="reasoning-field">
              <div class="setting-range">
                <div class="setting-range-header">
                  <span
                    class="setting-label"
                    title="Minimum duration (seconds) for each audio chunk."
                    >Min Chunk Duration</span
                  >
                  <span class="range-value"
                    >{draft.min_chunk_sec.toFixed(2)}s</span
                  >
                </div>
                <input
                  type="range"
                  class="range-input"
                  min="0.02"
                  max="0.5"
                  step="0.01"
                  value={draft.min_chunk_sec}
                  disabled={saving}
                  style="--slider-fill: {getSliderFill(
                    draft.min_chunk_sec,
                    0.02,
                    0.5,
                  )}"
                  on:input={(e) => {
                    draft = {
                      ...draft,
                      min_chunk_sec: parseFloat(
                        (e.target as HTMLInputElement).value,
                      ),
                    };
                    markDirty();
                  }}
                />
                <div class="range-extents">
                  <span>0.02s (responsive)</span>
                  <span>0.5s (chunky)</span>
                </div>
              </div>
            </div>
          </div>
        </div>
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

  /* Model + Presets row layout */
  .model-presets-row {
    display: flex;
    gap: 1.5rem;
    align-items: flex-start;
    flex-wrap: wrap;
    grid-column: 1 / -1; /* Span full width in parent grid */
  }

  .model-select-compact {
    flex: 1;
    min-width: 200px;
    max-width: 280px;
  }

  .presets-container {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    flex: 1;
    min-width: 180px;
  }

  .preset-select-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .preset-select-row .select-input {
    flex: 1;
    min-width: 120px;
  }

  .system-prompt-row {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
    margin-top: 0.5rem;
    grid-column: 1 / -1; /* Span full width in parent grid */
  }

  .disabled-field {
    opacity: 0.5;
    pointer-events: none;
  }
</style>
