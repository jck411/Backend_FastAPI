<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import { webSearchStore } from "../../chat/webSearchStore";
  import { presetsStore } from "../../stores/presets";

  interface SelectableModel {
    id: string;
    name?: string | null;
  }

  type ModelPickerComponent = typeof import("./ModelPicker.svelte").default;
  type WebSearchMenuComponent = typeof import("./WebSearchMenu.svelte").default;

  const dispatch = createEventDispatcher<{
    openExplorer: void;
    clear: void;
    modelChange: { id: string };
    openModelSettings: void;
    openSystemSettings: void;
    openSpeechSettings: void;
    openKioskSettings: void;
    openCliSettings: void;
    openPresets: void;
  }>();

  export let selectableModels: SelectableModel[] = [];
  export let selectedModel = "";
  export let modelsLoading = false;
  export let modelsError: string | null = null;
  export let hasMessages = false;
  let ModelPicker: ModelPickerComponent | null = null;
  let WebSearchMenu: WebSearchMenuComponent | null = null;
  let modelPickerLoading = false;
  let webSearchMenuLoading = false;

  async function loadModelPicker(): Promise<void> {
    if (ModelPicker) return;
    modelPickerLoading = true;
    try {
      const module = await import("./ModelPicker.svelte");
      ModelPicker = module.default;
    } catch (error) {
      console.error("Failed to load ModelPicker", error);
    } finally {
      modelPickerLoading = false;
    }
  }

  async function loadWebSearchMenu(): Promise<void> {
    if (WebSearchMenu) return;
    webSearchMenuLoading = true;
    try {
      const module = await import("./WebSearchMenu.svelte");
      WebSearchMenu = module.default;
    } catch (error) {
      console.error("Failed to load WebSearchMenu", error);
    } finally {
      webSearchMenuLoading = false;
    }
  }

  onMount(() => {
    void loadModelPicker();
    void loadWebSearchMenu();
  });

  function handleExplorerClick(): void {
    dispatch("openExplorer");
  }

  function handleClear(): void {
    dispatch("clear");
  }

  function forwardModelChange(event: CustomEvent<{ id: string }>): void {
    dispatch("modelChange", event.detail);
  }

  function forwardOpenModelSettings(): void {
    dispatch("openModelSettings");
  }

  function forwardOpenSystemSettings(): void {
    dispatch("openSystemSettings");
  }

  function forwardOpenSpeechSettings(): void {
    dispatch("openSpeechSettings");
  }

  function forwardOpenKioskSettings(): void {
    dispatch("openKioskSettings");
  }

  function forwardOpenCliSettings(): void {
    dispatch("openCliSettings");
  }

  function forwardOpenPresets(): void {
    dispatch("openPresets");
  }
</script>

<header class="topbar chat-header">
  <div class="topbar-content">
    <div class="controls">
      <button
        class="btn btn-ghost btn-small explorer"
        type="button"
        on:click={handleExplorerClick}
      >
        Explorer
      </button>

      {#if ModelPicker}
        <svelte:component
          this={ModelPicker}
          {selectableModels}
          {selectedModel}
          {modelsLoading}
          {modelsError}
          on:modelChange={forwardModelChange}
        />
      {:else}
        <div
          class="model-picker-loading"
          data-loading={modelPickerLoading}
          aria-hidden="true"
        >
          <select disabled>
            <option>Loading…</option>
          </select>
        </div>
      {/if}

      {#if WebSearchMenu}
        <svelte:component this={WebSearchMenu} />
      {:else}
        <div
          class="web-search-loading"
          data-loading={webSearchMenuLoading}
          aria-hidden="true"
        >
          <button
            class="btn btn-ghost btn-small web-search-summary"
            type="button"
            disabled
          >
            <span>Web search</span>
            <span class="status" data-enabled={$webSearchStore.enabled}>
              {$webSearchStore.enabled ? "On" : "Off"}
            </span>
          </button>
        </div>
      {/if}

      <button
        class="btn btn-ghost btn-small"
        type="button"
        on:click={forwardOpenModelSettings}
        aria-label="Model settings"
        title="Model settings"
        disabled={modelsLoading || !selectedModel}
      >
        <span>Model</span>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.89 3.31.876 2.42 2.42a1.724 1.724 0 0 0 1.066 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.572c.89 1.543-.876 3.31-2.42 2.42a1.724 1.724 0 0 0-2.572 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.89-3.31-.876-2.42-2.42a1.724 1.724 0 0 0-1.066-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.572c-.89-1.543.876-3.31 2.42-2.42.965.557 2.185.21 2.573-1.066Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <button
        class="btn btn-ghost btn-small"
        type="button"
        on:click={forwardOpenPresets}
        aria-label="Presets"
        title="Presets"
      >
        <span>Presets</span>
      </button>

      {#if $presetsStore.applying}
        <button
          class="preset-badge applying"
          type="button"
          on:click={forwardOpenPresets}
          aria-live="polite"
          title={`Applying ${$presetsStore.applying}… (click to manage presets)`}
        >
          <span class="spinner" aria-hidden="true"></span>
          <span class="label">Preset</span>
          <span class="name" title={$presetsStore.applying}
            >{$presetsStore.applying}</span
          >
        </button>
      {:else if $presetsStore.lastApplied}
        <button
          class="preset-badge"
          type="button"
          on:click={forwardOpenPresets}
          aria-live="polite"
          title={`Active preset: ${$presetsStore.lastApplied} (click to manage)`}
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="label">Preset</span>
          <span class="name" title={$presetsStore.lastApplied}
            >{$presetsStore.lastApplied}</span
          >
        </button>
      {/if}

      <button
        class="btn btn-ghost btn-small system-settings"
        type="button"
        on:click={forwardOpenSystemSettings}
        aria-label="System settings"
        title="System settings"
      >
        <span>System</span>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.89 3.31.876 2.42 2.42a1.724 1.724 0 0 0 1.066 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.572c.89 1.543-.876 3.31-2.42 2.42a1.724 1.724 0 0 0-2.572 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.89-3.31-.876-2.42-2.42a1.724 1.724 0 0 0-1.066-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.572c-.89-1.543.876-3.31 2.42-2.42.965.557 2.185.21 2.573-1.066Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <button
        class="btn btn-ghost btn-small"
        type="button"
        on:click={forwardOpenSpeechSettings}
        aria-label="Speech settings"
        title="Speech settings"
      >
        <span>Speech</span>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.89 3.31.876 2.42 2.42a1.724 1.724 0 0 0 1.066 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.572c.89 1.543-.876 3.31-2.42 2.42a1.724 1.724 0 0 0-2.572 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.89-3.31-.876-2.42-2.42a1.724 1.724 0 0 0-1.066-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.572c-.89-1.543.876-3.31 2.42-2.42.965.557 2.185.21 2.573-1.066Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <button
        class="btn btn-ghost btn-small kiosk-btn"
        type="button"
        on:click={forwardOpenKioskSettings}
        aria-label="Kiosk settings"
        title="Kiosk settings"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <!-- Screen/display -->
          <rect
            x="4"
            y="2"
            width="16"
            height="12"
            rx="1.5"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <!-- Stand -->
          <path
            d="M12 14v4M8 22h8M8 18h8"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </svg>
      </button>

      <button
        class="btn btn-ghost btn-small cli-btn"
        type="button"
        on:click={forwardOpenCliSettings}
        aria-label="CLI settings"
        title="CLI settings"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
            <path d="M4 17l6-6-6-6M12 19h8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>

      <button
        class="btn btn-ghost btn-small"
        type="button"
        on:click={handleClear}
        disabled={!hasMessages}
      >
        Clear
      </button>
    </div>
  </div>
</header>

<style>
  .topbar {
    height: var(--header-h);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    background: transparent;
    position: relative;
    z-index: 20;
    padding: 2rem 2rem 1rem;
  }
  .topbar-content {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
  }
  .controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: nowrap;
  }
  .controls > * {
    flex: 0 0 auto;
  }
  :global(.chat-header .controls .model-picker) {
    display: flex;
  }
  :global(.chat-header .controls .model-picker),
  :global(.chat-header .controls .web-search) {
    width: auto;
  }
  .preset-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    border: 1px solid #25314d;
    background: rgba(12, 19, 34, 0.7);
    color: #c8d6ef;
    font-size: 0.8rem;
    white-space: nowrap;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease,
      box-shadow 0.2s ease;
  }
  .preset-badge:hover,
  .preset-badge:focus-visible {
    border-color: #38bdf8;
    color: #f2f6ff;
    background: rgba(12, 22, 40, 0.85);
    outline: none;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25);
  }
  .preset-badge .label {
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    color: #9fb3d8;
  }
  .preset-badge .name {
    max-width: 14ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #e5edff;
  }
  /* Small indicator dot for active state */
  .preset-badge .dot {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 999px;
    background: #22c55e;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.15);
  }
  /* Spinner when applying */
  .preset-badge.applying .spinner {
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 999px;
    border: 2px solid rgba(148, 187, 233, 0.25);
    border-top-color: #38bdf8;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
  :global(.chat-header .controls select) {
    appearance: none;
    padding: 0.45rem 2rem 0.45rem 0.75rem;
    border-radius: 0.5rem;
    background-color: rgba(9, 14, 26, 0.92);
    color: #f3f5ff;
    border: 1px solid rgba(37, 49, 77, 0.9);
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease;
    background-image: url('data:image/svg+xml,%3Csvg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Cpath d="M7 8l3 3 3-3" stroke="%23d4daee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/%3E%3C/svg%3E');
    background-repeat: no-repeat;
    background-position: right 0.65rem center;
    background-size: 0.9rem;
    min-width: 160px;
    font: inherit;
  }
  :global(.chat-header .controls select:hover) {
    border-color: #38bdf8;
    background-color: rgba(12, 19, 34, 0.95);
    color: #f8fafc;
  }
  :global(.chat-header .controls select:focus) {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
    border-color: #38bdf8;
    box-shadow: none;
  }
  :global(.chat-header .controls select:disabled) {
    opacity: 0.6;
    cursor: not-allowed;
    background-color: rgba(9, 14, 26, 0.6);
  }
  :global(.chat-header .controls select option) {
    background: #0a101a;
    color: #f3f5ff;
  }
  :global(.chat-header .controls .btn) {
    white-space: nowrap;
  }
  :global(.chat-header .controls .btn.system-settings svg) {
    width: 1.05rem;
    height: 1.05rem;
  }
  .model-picker-loading,
  .web-search-loading {
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
  }
  .web-search-loading .status {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(62, 90, 140, 0.6);
    color: #9fb3d8;
  }
  @media (max-width: 1280px) {
    .topbar {
      height: auto;
      padding: 0.75rem 1.5rem 1rem;
    }
    .topbar-content {
      flex-direction: column;
      align-items: stretch;
      gap: 0.75rem;
      width: 100%;
      max-width: 900px;
      margin: 0 auto;
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      align-items: stretch;
      width: 100%;
      max-width: 900px;
      margin: 0 auto;
      gap: 0.75rem;
      justify-items: stretch;
    }
    .controls > * {
      width: 100%;
      min-width: 0;
    }
    :global(.chat-header .controls .btn),
    :global(.chat-header .controls select),
    .preset-badge,
    .model-picker-loading,
    .web-search-loading,
    :global(.chat-header .controls .model-picker),
    :global(.chat-header .controls .web-search) {
      width: 100%;
    }
    :global(.chat-header .controls .btn),
    .preset-badge {
      justify-content: center;
    }
    :global(.chat-header .controls select) {
      min-width: 0;
      text-align: left;
    }
    :global(.chat-header .controls .explorer) {
      grid-column: 1;
    }
    :global(.chat-header .controls .model-picker),
    .model-picker-loading {
      grid-column: 2;
    }
    .preset-badge {
      grid-column: 1 / -1;
      order: 9;
    }
    .web-search-loading {
      justify-content: center;
    }
  }
  @media (max-width: 1024px) {
    .topbar {
      padding: 0.75rem 1.25rem 1rem;
    }
    .controls {
      gap: 0.65rem;
    }
  }
  @media (max-width: 768px) {
    .topbar {
      padding: 0.75rem 1.15rem 0.75rem;
    }
    .topbar-content {
      max-width: 100%;
    }
    .controls {
      max-width: 100%;
    }
    :global(.chat-header .controls .btn),
    :global(.chat-header .controls select) {
      padding: 0.55rem 0.9rem;
    }
    :global(.chat-header .controls .btn.system-settings svg) {
      width: 1rem;
      height: 1rem;
    }
  }
  @media (max-width: 480px) {
    .topbar {
      padding: 0.75rem 1rem 0.5rem;
    }
    .preset-badge .name {
      max-width: 20ch;
    }
  }
</style>
