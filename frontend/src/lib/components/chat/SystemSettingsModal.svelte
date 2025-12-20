<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { get } from "svelte/store";
  import type { PresetListItem } from "../../api/types";
  import { chatStore } from "../../stores/chat";
  import { createGoogleAuthStore } from "../../stores/googleAuth";
  import { modelSettingsStore } from "../../stores/modelSettings";
  import { createMonarchAuthStore } from "../../stores/monarchAuth";
  import { presetsStore } from "../../stores/presets";
  import {
    DEEPGRAM_MODEL_OPTIONS,
    SPEECH_TIMING_PRESETS,
    type SpeechSettings,
    type SpeechTimingPresetKey,
    getDefaultSpeechSettings,
    speechSettingsStore,
  } from "../../stores/speechSettings";
  import { createSpotifyAuthStore } from "../../stores/spotifyAuth";
  import { createSystemPromptStore } from "../../stores/systemPrompt";
  import { suggestionsStore } from "../../stores/suggestions";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./system-settings.css";
  import "./speech-settings.css";
  import "./presets-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const systemPrompt = createSystemPromptStore();
  const googleAuth = createGoogleAuthStore();
  const monarchAuth = createMonarchAuthStore();
  const spotifyAuth = createSpotifyAuthStore();

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
      googleAuth.reset();
      spotifyAuth.reset();
      resetSpeechState();
      resetPresetDraft();
    }
  }

  async function initialize(): Promise<void> {
    await Promise.all([
      systemPrompt.load(),
      googleAuth.load(),
      monarchAuth.load(),
      spotifyAuth.load(),
      presetsStore.load(),
    ]);
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
    if (closing || $systemPrompt.saving || speechSaving || $googleAuth.authorizing) {
      return;
    }

    closing = true;

    const promptSaved = await flushSystemPrompt();
    const speechSaved = await flushSpeechSettings();

    const promptState = get(systemPrompt);

    if (promptSaved && speechSaved && !promptState.saveError) {
      dispatch("close");
    }

    closing = false;
  }

  let monarchEmail = "";
  let monarchPassword = "";
  let monarchMfaSecret = "";
  let showMonarchPassword = false;
  let creatingName = "";
  let confirmingDelete: string | null = null;
  let speechDraft: SpeechSettings = initializeSpeechDraft();
  let speechDirty = false;
  let speechSaving = false;
  let speechStatusMessage: string | null = null;
  let speechStatusVariant: "success" | "error" | "pending" | "info" | null =
    null;

  function saveMonarch(): void {
    if (!monarchEmail || !monarchPassword) return;
    monarchAuth.save({
      email: monarchEmail,
      password: monarchPassword,
      mfa_secret: monarchMfaSecret || null,
    });
  }

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
  }

  async function handleSaveSnapshot(item: PresetListItem): Promise<void> {
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
    speechStatusMessage = "Changes save when you close system settings.";
    speechStatusVariant = "info" as const;
  }

  function markSpeechDirty(
    message: string | null = null,
    variant: "success" | "error" | "pending" | null = "pending",
  ): void {
    speechDirty = true;
    speechStatusMessage = message;
    speechStatusVariant = variant ?? "pending";
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
    markSpeechDirty();
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
        utteranceEndMs: preset.stt.utteranceEndMs,
        endpointing: preset.stt.endpointing,
        autoSubmitDelayMs: preset.stt.autoSubmitDelayMs,
      },
    };
    markSpeechDirty(
      `${preset.label} preset applied; closing system settings will save.`,
      "pending",
    );
  }

  async function flushSpeechSettings(): Promise<boolean> {
    if (!speechDirty) {
      return true;
    }

    speechSaving = true;
    speechStatusMessage = "Saving changes…";
    speechStatusVariant = "pending";

    try {
      const saved = speechSettingsStore.save(speechDraft);
      speechDraft = {
        ...saved,
        stt: { ...saved.stt },
      };
      speechDirty = false;
      speechStatusMessage = "Saved";
      speechStatusVariant = "success";
      return true;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to save speech settings.";
      speechStatusMessage = message;
      speechStatusVariant = "error";
      return false;
    } finally {
      speechSaving = false;
    }
  }

  function handleSpeechReset(): void {
    speechDraft = getDefaultSpeechSettings();
    speechDirty = true;
    speechStatusMessage = "Defaults restored; closing system settings will save.";
    speechStatusVariant = "pending";
  }

  function refreshGoogleAuth(): void {
    if ($googleAuth.loading || $googleAuth.authorizing) {
      return;
    }
    void googleAuth.load();
  }

  async function startGoogleAuthorization(): Promise<void> {
    if ($googleAuth.authorizing) {
      return;
    }
    await googleAuth.authorize();
  }

  function refreshSpotifyAuth(): void {
    if ($spotifyAuth.loading || $spotifyAuth.authorizing) {
      return;
    }
    void spotifyAuth.load();
  }

  async function startSpotifyAuthorization(): Promise<void> {
    if ($spotifyAuth.authorizing) {
      return;
    }
    await spotifyAuth.authorize();
  }

  function formatUpdatedAt(timestamp: string | null): string | null {
    if (!timestamp) return null;
    try {
      const date = new Date(timestamp);
      if (Number.isNaN(date.getTime())) {
        return timestamp;
      }
      return new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        year: "numeric",
        month: "short",
        day: "2-digit",
      }).format(date);
    } catch (error) {
      console.warn("Failed to format timestamp", error);
      return timestamp;
    }
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
    closeDisabled={$systemPrompt.saving ||
      speechSaving ||
      $googleAuth.authorizing}
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
            disabled={!$systemPrompt.dirty ||
              $systemPrompt.saving}
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
          ></textarea>
          {#if $systemPrompt.saveError}
            <p class="status error">{$systemPrompt.saveError}</p>
          {:else if $systemPrompt.dirty}
            <p class="status">Pending changes; closing this modal will save.</p>
          {:else}
            <p class="status muted">Changes save when you close this modal.</p>
          {/if}
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Google services</h3>
          <p class="system-card-caption">
            Connect Calendar, Tasks, Gmail, and Drive with a single consent.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-primary btn-small"
            on:click={() => void startGoogleAuthorization()}
            disabled={$googleAuth.loading || $googleAuth.authorizing}
          >
            {$googleAuth.authorizing
              ? "Authorizing…"
              : $googleAuth.authorized
                ? "Reconnect Google Services"
                : "Connect Google Services"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $googleAuth.loading}
          <p class="status">Checking Google authorization…</p>
        {:else if $googleAuth.error}
          <p class="status error">{$googleAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="btn btn-ghost btn-small"
              on:click={refreshGoogleAuth}
              disabled={$googleAuth.loading || $googleAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $googleAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$googleAuth.userEmail}</span
            >.
          </p>
          {#if $googleAuth.expiresAt}
            <p class="status muted">
              Current token expires {formatUpdatedAt($googleAuth.expiresAt) ??
                "soon"}.
            </p>
          {:else}
            <p class="status muted">Access will refresh automatically.</p>
          {/if}
        {:else}
          <p class="status">Google services are not connected.</p>
        {/if}

        <ul class="google-services-list">
          {#each $googleAuth.services as service}
            <li>{service}</li>
          {/each}
        </ul>

        <p class="status muted">
          Click "Connect Google Services" to authorize these integrations for
          the assistant.
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Spotify</h3>
          <p class="system-card-caption">
            Connect Spotify for music control and playback.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-primary btn-small"
            on:click={() => void startSpotifyAuthorization()}
            disabled={$spotifyAuth.loading || $spotifyAuth.authorizing}
          >
            {$spotifyAuth.authorizing
              ? "Authorizing…"
              : $spotifyAuth.authorized
                ? "Reconnect Spotify"
                : "Connect Spotify"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $spotifyAuth.loading}
          <p class="status">Checking Spotify authorization…</p>
        {:else if $spotifyAuth.error}
          <p class="status error">{$spotifyAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="btn btn-ghost btn-small"
              on:click={refreshSpotifyAuth}
              disabled={$spotifyAuth.loading || $spotifyAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $spotifyAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$spotifyAuth.userEmail}</span
            >.
          </p>
          <p class="status muted">Access will refresh automatically.</p>
        {:else}
          <p class="status">Spotify is not connected.</p>
        {/if}

        <p class="status muted">
          Click "Connect Spotify" to authorize music control and playback
          features.
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Monarch Money</h3>
          <p class="system-card-caption">Connect your Monarch Money account.</p>
        </div>
        <div class="system-card-actions">
          {#if $monarchAuth.configured}
            <button
              type="button"
              class="btn btn-ghost btn-small"
              on:click={() => monarchAuth.remove()}
              disabled={$monarchAuth.saving}
            >
              Disconnect
            </button>
          {:else}
            <button
              type="button"
              class="btn btn-primary btn-small"
              on:click={saveMonarch}
              disabled={$monarchAuth.saving ||
                !monarchEmail ||
                !monarchPassword}
            >
              {$monarchAuth.saving ? "Saving..." : "Connect"}
            </button>
          {/if}
        </div>
      </header>

      <div class="system-card-body">
        {#if $monarchAuth.loading}
          <p class="status">Checking Monarch status…</p>
        {:else if $monarchAuth.configured}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$monarchAuth.email}</span
            >.
          </p>
        {:else}
          <div class="monarch-form">
            <label>
              Email
              <input
                type="email"
                class="input-control"
                bind:value={monarchEmail}
                placeholder="email@example.com"
              />
            </label>
            <label>
              Password
              <div class="password-input-wrapper">
                <input
                  class="input-control"
                  type={showMonarchPassword ? "text" : "password"}
                  bind:value={monarchPassword}
                  placeholder="Password"
                />
                <button
                  type="button"
                  class="btn btn-ghost btn-icon btn-small"
                  on:click={() => (showMonarchPassword = !showMonarchPassword)}
                  title={showMonarchPassword
                    ? "Hide password"
                    : "Show password"}
                >
                  {#if showMonarchPassword}
                    <!-- Eye Off Icon -->
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path
                        d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
                      ></path>
                      <line x1="1" y1="1" x2="23" y2="23"></line>
                    </svg>
                  {:else}
                    <!-- Eye Icon -->
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"
                      ></path>
                      <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                  {/if}
                </button>
              </div>
            </label>
            <label>
              MFA Secret (Optional)
              <input
                type="text"
                class="input-control"
                bind:value={monarchMfaSecret}
                placeholder="MFA Secret"
              />
            </label>
            <p
              class="status muted"
              style="margin-top: -0.5rem; margin-bottom: 1rem; font-size: 0.8em;"
            >
              If you already use an app, you must <strong>reset MFA</strong> in Monarch
              Settings to see the secret key again. Enter the new key here AND in
              your app.
            </p>
            {#if $monarchAuth.error}
              <p class="status error">{$monarchAuth.error}</p>
            {/if}
          </div>
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
          <h3>Speech settings</h3>
          <p class="system-card-caption">
            Configure Deepgram speech-to-text dictation settings.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="btn btn-ghost btn-small"
            on:click={handleSpeechReset}
            disabled={speechSaving}
          >
            Reset to defaults
          </button>
        </div>
      </header>

      <div class="system-card-body">
        <div class="speech-card">
          <div class="speech-card-header">
            <h3>Deepgram model</h3>
            <p>Choose the speech-to-text engine and helper features.</p>
          </div>

          <div class="model-presets-row">
            <div class="speech-field">
              <span class="field-label">Model</span>
              <select
                class="select-control"
                value={speechDraft.stt.model}
                on:change={(event) =>
                  updateSpeechStt(
                    "model",
                    (event.target as HTMLSelectElement).value,
                  )}
              >
                {#each DEEPGRAM_MODEL_OPTIONS as option}
                  <option value={option.value}>{option.label}</option>
                {/each}
              </select>
            </div>
            <div class="speech-field presets-field">
              <span class="field-label">Speech timing presets</span>
              <div class="speech-presets" aria-label="Timing presets">
                <button
                  class="btn btn-soft btn-small"
                  type="button"
                  on:click={() => applySpeechPreset("fast")}
                >
                  Fast
                </button>
                <button
                  class="btn btn-soft btn-small"
                  type="button"
                  on:click={() => applySpeechPreset("normal")}
                >
                  Normal
                </button>
                <button
                  class="btn btn-soft btn-small"
                  type="button"
                  on:click={() => applySpeechPreset("slow")}
                >
                  Slow
                </button>
              </div>
            </div>
          </div>

          <div class="toggle-grid">
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.interimResults}
                on:change={(event) =>
                  updateSpeechStt(
                    "interimResults",
                    (event.target as HTMLInputElement).checked,
                  )}
              />
              <span>Interim transcripts</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.vadEvents}
                on:change={(event) =>
                  updateSpeechStt(
                    "vadEvents",
                    (event.target as HTMLInputElement).checked,
                  )}
              />
              <span>VAD events</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.smartFormat}
                on:change={(event) =>
                  updateSpeechStt(
                    "smartFormat",
                    (event.target as HTMLInputElement).checked,
                  )}
              />
              <span>Smart formatting</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.punctuate}
                on:change={(event) =>
                  updateSpeechStt(
                    "punctuate",
                    (event.target as HTMLInputElement).checked,
                  )}
              />
              <span>Punctuation</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.numerals}
                on:change={(event) =>
                  updateSpeechStt(
                    "numerals",
                    (event.target as HTMLInputElement).checked,
                  )}
              />
              <span>Numerals</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.fillerWords}
                on:change={(event) =>
                  updateSpeechStt(
                    "fillerWords",
                    (event.target as HTMLInputElement).checked,
                  )}
              />
              <span>Keep filler words</span>
            </label>
            <label class="toggle-item">
              <input
                type="checkbox"
                checked={speechDraft.stt.profanityFilter}
                on:change={(event) =>
                  updateSpeechStt(
                    "profanityFilter",
                    (event.target as HTMLInputElement).checked,
                  )}
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
                class="input-control"
                type="number"
                min="300"
                max="5000"
                step="50"
                value={speechDraft.stt.endpointing}
                on:change={(event) =>
                  handleSpeechNumberInput(event, (value) =>
                    updateSpeechStt("endpointing", value),
                  )}
              />
              <p class="speech-hint">
                How long Deepgram waits after silence before finalizing the
                transcript.
              </p>
            </div>
            <div class="speech-field">
              <span class="field-label">Utterance gap (ms)</span>
              <input
                class="input-control"
                type="number"
                min="500"
                max="5000"
                step="50"
                value={speechDraft.stt.utteranceEndMs}
                on:change={(event) =>
                  handleSpeechNumberInput(event, (value) =>
                    updateSpeechStt("utteranceEndMs", value),
                  )}
              />
              <p class="speech-hint">
                Silence between words before Deepgram starts a new interim
                segment.
              </p>
            </div>
          </div>

          <div class="auto-submit-block">
            <div class="auto-submit-row">
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
                <span class="field-label">Auto-submit</span>
              </label>
              <p class="speech-hint">
                Send automatically when speech ends. Delay waits after
                endpointing.
              </p>
            </div>
            <div class="delay-inline">
              <label class="delay-label" for="auto-submit-delay-input">
                Delay (ms)
              </label>
              <input
                id="auto-submit-delay-input"
                class="input-control"
                type="number"
                min="0"
                max="20000"
                step="50"
                value={speechDraft.stt.autoSubmitDelayMs}
                disabled={!speechDraft.stt.autoSubmit}
                on:change={(event) =>
                  handleSpeechNumberInput(event, (value) =>
                    updateSpeechStt("autoSubmitDelayMs", value),
                  )}
              />
            </div>
          </div>
        </div>

        <div class="speech-status">
          {#if speechStatusVariant === "error"}
            <p class="status" data-variant="error" aria-live="assertive">
              {speechStatusMessage}
            </p>
          {:else if speechSaving}
            <p class="status" data-variant="pending" aria-live="polite">
              Saving changes…
            </p>
          {:else if speechDirty}
            <p class="status" data-variant="pending" aria-live="polite">
              {speechStatusMessage ??
                "Pending changes; closing system settings will save."}
            </p>
          {:else}
            <p
              class="status"
              data-variant={speechStatusVariant ?? "info"}
              aria-live="polite"
            >
              {speechStatusMessage ??
                "Changes save when you close system settings."}
            </p>
          {/if}
        </div>
      </div>
    </article>

    <footer slot="footer" class="model-settings-footer system-settings-footer">
      {#if $systemPrompt.saveError || speechStatusVariant === "error"}
        <p class="status error">Resolve the errors above before closing.</p>
      {:else if $systemPrompt.saving || speechSaving}
        <p class="status">Saving changes…</p>
      {:else if $systemPrompt.dirty || speechDirty}
        <p class="status">Pending changes; closing this modal will save.</p>
      {:else}
        <p class="status">Changes save when you close this modal.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
