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
    openKioskSettings: void;
    openCliSettings: void;
    openMcpServers: void;
    drawerToggle: { open: boolean };
  }>();

  export let selectableModels: SelectableModel[] = [];
  export let selectedModel = "";
  export let modelsLoading = false;
  export let modelsError: string | null = null;
  export let hasMessages = false;
  export let pwaMode = false;
  let ModelPicker: ModelPickerComponent | null = null;
  let WebSearchMenu: WebSearchMenuComponent | null = null;
  let modelPickerLoading = false;
  let webSearchMenuLoading = false;
  let controlsOpen = false;

  $: dispatch("drawerToggle", { open: controlsOpen });

  function closeDrawer(): void {
    controlsOpen = false;
  }

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
    closeDrawer();
    dispatch("openExplorer");
  }

  function handleClear(): void {
    closeDrawer();
    dispatch("clear");
  }

  function forwardModelChange(event: CustomEvent<{ id: string }>): void {
    dispatch("modelChange", event.detail);
  }

  function forwardOpenModelSettings(): void {
    closeDrawer();
    dispatch("openModelSettings");
  }

  function forwardOpenSystemSettings(): void {
    closeDrawer();
    dispatch("openSystemSettings");
  }

  function forwardOpenKioskSettings(): void {
    closeDrawer();
    dispatch("openKioskSettings");
  }

  function forwardOpenCliSettings(): void {
    closeDrawer();
    dispatch("openCliSettings");
  }

  function forwardOpenMcpServers(): void {
    closeDrawer();
    dispatch("openMcpServers");
  }
</script>

<header
  class="topbar chat-header"
  data-pwa-mode={pwaMode}
  data-drawer-open={controlsOpen}
>
  <!-- Mobile hamburger bar (≤768px) -->
  <div class="mobile-bar">
    <button
      class="hamburger-btn"
      type="button"
      aria-label={controlsOpen ? "Close menu" : "Open menu"}
      aria-expanded={controlsOpen}
      aria-controls="chat-header-controls"
      on:click={() => (controlsOpen = !controlsOpen)}
    >
      {#if controlsOpen}
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M18 6L6 18M6 6l12 12"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
          />
        </svg>
      {:else}
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M4 6h16M4 12h16M4 18h16"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
          />
        </svg>
      {/if}
    </button>
    <span class="mobile-model-name">
      {#if selectedModel}
        {selectableModels.find((m) => m.id === selectedModel)?.name ??
          selectedModel.split("/").pop() ??
          "Chat"}
      {:else}
        Chat
      {/if}
    </span>
    <button
      class="btn btn-ghost btn-small mobile-clear"
      type="button"
      on:click={handleClear}
      disabled={!hasMessages}
      aria-label="Clear conversation"
    >
      Clear
    </button>
  </div>

  <!-- Desktop topbar content -->
  <div class="topbar-content">
    <div class="controls" id="chat-header-controls">
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

      {#if $presetsStore.applying}
        <button
          class="preset-badge applying"
          type="button"
          on:click={forwardOpenSystemSettings}
          aria-live="polite"
          title={`Applying ${$presetsStore.applying}… (open system settings to manage presets)`}
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
          on:click={forwardOpenSystemSettings}
          aria-live="polite"
          title={`Active preset: ${$presetsStore.lastApplied} (open system settings to manage)`}
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="label">Preset</span>
          <span class="name" title={$presetsStore.lastApplied}
            >{$presetsStore.lastApplied}</span
          >
        </button>
      {/if}

      <div class="icon-row">
        <button
          class="btn btn-ghost btn-small settings-icon mcp-btn"
          type="button"
          on:click={forwardOpenMcpServers}
          aria-label="MCP servers"
          title="MCP servers"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 195 195"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <path
              d="M25 97.8528L92.8823 29.9706C102.255 20.598 117.451 20.598 126.823 29.9706V29.9706C136.196 39.3431 136.196 54.5391 126.823 63.9117L75.5581 115.177"
              stroke="currentColor"
              stroke-width="12"
              stroke-linecap="round"
            />
            <path
              d="M76.2653 114.47L126.823 63.9117C136.196 54.5391 151.392 54.5391 160.765 63.9117L161.118 64.2652C170.491 73.6378 170.491 88.8338 161.118 98.2063L99.7248 159.6C96.6006 162.724 96.6006 167.789 99.7248 170.913L112.331 183.52"
              stroke="currentColor"
              stroke-width="12"
              stroke-linecap="round"
            />
            <path
              d="M109.853 46.9411L59.6482 97.1457C50.2757 106.518 50.2757 121.714 59.6482 131.087V131.087C69.0208 140.459 84.2168 140.459 93.5894 131.087L143.794 80.8822"
              stroke="currentColor"
              stroke-width="12"
              stroke-linecap="round"
            />
          </svg>
        </button>

        <button
          class="btn btn-ghost btn-small settings-icon system-settings"
          type="button"
          on:click={forwardOpenSystemSettings}
          aria-label="System settings"
          title="System settings"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <rect
              x="3"
              y="4"
              width="18"
              height="12"
              rx="2"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M8 20h8"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M3 8h18"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
        </button>

        <button
          class="btn btn-ghost btn-small settings-icon kiosk-btn"
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
          class="btn btn-ghost btn-small settings-icon cli-btn"
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
            <path
              d="M4 17l6-6-6-6M12 19h8"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
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
  </div>

  <!-- Mobile drawer backdrop -->
  {#if controlsOpen}
    <button
      class="drawer-backdrop"
      type="button"
      aria-label="Close menu"
      tabindex="-1"
      on:click={() => (controlsOpen = false)}
    ></button>
  {/if}
</header>

<style>
  /* ── Base (desktop) ── */
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
  .mobile-bar {
    display: none;
  }
  .drawer-backdrop {
    display: none;
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
  .icon-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
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
  .preset-badge .dot {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 999px;
    background: #22c55e;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.15);
  }
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
  :global(.chat-header .controls .btn.settings-icon svg) {
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

  /* ── Tablet breakpoint ── */
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
    .icon-row {
      grid-column: 1 / -1;
      justify-content: center;
      flex-wrap: nowrap;
    }
    .icon-row :global(.btn) {
      width: auto;
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

  /* ── Mobile: hamburger + slide-out drawer ── */
  @media (max-width: 768px) {
    .topbar {
      height: auto;
      padding: 0;
      flex-direction: column;
      align-items: stretch;
    }

    /* Thin always-visible bar */
    .mobile-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      padding-top: max(0.5rem, env(safe-area-inset-top, 0));
      background: rgba(4, 6, 13, 0.97);
      border-bottom: 1px solid rgba(37, 49, 77, 0.5);
      position: relative;
      z-index: 52;
    }
    .hamburger-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      padding: 0;
      border: none;
      border-radius: 0.5rem;
      background: transparent;
      color: #c8d6ef;
      cursor: pointer;
      transition:
        background 0.15s ease,
        color 0.15s ease;
      flex-shrink: 0;
    }
    .hamburger-btn:hover,
    .hamburger-btn:focus-visible {
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      outline: none;
    }
    .mobile-model-name {
      flex: 1;
      text-align: center;
      font-size: 0.8rem;
      color: #9fb3d8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      padding: 0 0.25rem;
    }
    .mobile-clear {
      flex-shrink: 0;
      font-size: 0.78rem;
      padding: 0.3rem 0.7rem;
    }

    /* Desktop topbar-content becomes the drawer */
    .topbar-content {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: min(300px, 80vw);
      background: rgba(6, 10, 20, 0.98);
      border-right: 1px solid rgba(37, 49, 77, 0.6);
      padding: 1rem;
      padding-top: calc(max(0.5rem, env(safe-area-inset-top, 0)) + 3rem);
      overflow-y: auto;
      z-index: 51;
      transform: translateX(-100%);
      transition: transform 0.25s ease;
      flex-direction: column;
      backdrop-filter: blur(16px);
    }
    .topbar[data-drawer-open="true"] .topbar-content {
      transform: translateX(0);
    }

    .controls {
      display: flex;
      flex-direction: column;
      gap: 0.65rem;
      max-width: 100%;
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
    :global(.chat-header .controls .btn) {
      justify-content: flex-start;
      padding: 0.6rem 0.75rem;
    }
    :global(.chat-header .controls select) {
      min-width: 0;
      width: 100%;
    }
    .icon-row {
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: flex-start;
    }
    .icon-row :global(.btn) {
      width: auto;
    }
    .preset-badge {
      width: 100%;
      justify-content: flex-start;
    }

    /* Backdrop overlay */
    .drawer-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 50;
      background: rgba(0, 0, 0, 0.5);
      border: none;
      padding: 0;
      cursor: default;
    }
    .topbar[data-drawer-open="true"] .drawer-backdrop {
      display: block;
    }
  }

  @media (max-width: 480px) {
    .preset-badge .name {
      max-width: 20ch;
    }
  }
</style>
