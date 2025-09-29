<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";
  import type { WebSearchSettings } from "../../stores/chat";

  const dispatch = createEventDispatcher<{
    webSearchChange: { settings: Partial<WebSearchSettings> };
  }>();

  export let webSearch: WebSearchSettings = {
    enabled: false,
    engine: null,
    maxResults: null,
    searchPrompt: "",
    contextSize: null,
  };

  let menuOpen = false;
  let closeTimeout: ReturnType<typeof setTimeout> | null = null;
  let wasEnabled = webSearch.enabled;

  function sendChange(settings: Partial<WebSearchSettings>): void {
    dispatch("webSearchChange", { settings });
  }

  function cancelClose(): void {
    if (!closeTimeout) return;
    clearTimeout(closeTimeout);
    closeTimeout = null;
  }

  function openMenu(): void {
    cancelClose();
    menuOpen = true;
  }

  function scheduleClose(): void {
    cancelClose();
    closeTimeout = setTimeout(() => {
      menuOpen = false;
      closeTimeout = null;
    }, 250);
  }

  function closeMenu(): void {
    cancelClose();
    menuOpen = false;
  }

  function openIfEnabled(): void {
    if (!webSearch.enabled) return;
    openMenu();
  }

  function handleButtonClick(): void {
    if (webSearch.enabled) {
      sendChange({ enabled: false });
      closeMenu();
    } else {
      sendChange({ enabled: true });
      openMenu();
    }
  }

  function handleEngine(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement | null;
    if (!target) return;
    const value = target.value;
    if (value === "native" || value === "exa") {
      sendChange({ engine: value });
    } else {
      sendChange({ engine: null });
    }
  }

  function handleContext(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement | null;
    if (!target) return;
    const value = target.value;
    if (value === "low" || value === "medium" || value === "high") {
      sendChange({ contextSize: value });
    } else {
      sendChange({ contextSize: null });
    }
  }

  function handleMaxResults(event: Event): void {
    const target = event.currentTarget as HTMLInputElement | null;
    if (!target) return;
    const raw = target.value.trim();
    if (!raw) {
      sendChange({ maxResults: null });
      return;
    }
    sendChange({ maxResults: Number(raw) });
  }

  function handlePrompt(event: Event): void {
    const target = event.currentTarget as HTMLTextAreaElement | null;
    if (!target) return;
    sendChange({ searchPrompt: target.value });
  }

  function handleFocusOut(event: FocusEvent): void {
    const container = event.currentTarget as HTMLElement | null;
    const nextTarget = event.relatedTarget as Node | null;
    if (!container || !nextTarget || !container.contains(nextTarget)) {
      closeMenu();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
    }
  }

  $: if (!webSearch.enabled && wasEnabled) {
    closeMenu();
  }
  $: wasEnabled = webSearch.enabled;

  onDestroy(cancelClose);
</script>

<div
  class="web-search"
  data-enabled={webSearch.enabled}
  data-open={menuOpen}
  role="group"
  aria-label="Web search settings"
  on:mouseenter={openIfEnabled}
  on:mouseleave={scheduleClose}
  on:focusin={openIfEnabled}
  on:focusout={handleFocusOut}
>
  <button
    type="button"
    class="ghost web-search-summary"
    aria-haspopup="true"
    aria-expanded={webSearch.enabled && menuOpen}
    on:keydown={handleKeydown}
    on:click={handleButtonClick}
  >
    <span>Web search</span>
    <span class="status" data-enabled={webSearch.enabled}>
      {webSearch.enabled ? "On" : "Off"}
    </span>
  </button>
  {#if menuOpen && webSearch.enabled}
    <div class="web-search-menu">
      <div class="web-search-fields" aria-disabled={!webSearch.enabled}>
        <label>
          <span>Engine</span>
          <select
            value={webSearch.engine ?? ""}
            disabled={!webSearch.enabled}
            on:change={handleEngine}
          >
            <option value="">Auto</option>
            <option value="native">Native</option>
            <option value="exa">Exa</option>
          </select>
        </label>
        <label>
          <span>Context</span>
          <select
            value={webSearch.contextSize ?? ""}
            disabled={!webSearch.enabled}
            on:change={handleContext}
          >
            <option value="">Default</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>
        <label>
          <span>Max results</span>
          <input
            type="number"
            min="1"
            max="25"
            step="1"
            value={webSearch.maxResults ?? ""}
            disabled={!webSearch.enabled}
            on:input={handleMaxResults}
          />
        </label>
        <label class="prompt">
          <span>Search prompt</span>
          <textarea
            rows="2"
            value={webSearch.searchPrompt}
            disabled={!webSearch.enabled}
            placeholder="Use default prompt"
            on:input={handlePrompt}
          ></textarea>
        </label>
      </div>
    </div>
  {/if}
</div>

<style>
  .web-search {
    position: relative;
    display: inline-flex;
    align-items: center;
  }
  .web-search-summary {
    gap: 0.5rem;
  }
  .web-search[data-open="true"] .web-search-summary {
    border-color: #38bdf8;
    color: #38bdf8;
  }
  .web-search .status {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(62, 90, 140, 0.6);
    color: #9fb3d8;
  }
  .web-search .status[data-enabled="true"] {
    border-color: rgba(56, 189, 248, 0.4);
    color: #7dd3fc;
  }
  .web-search-menu {
    display: none;
    position: absolute;
    top: calc(100% + 0.25rem);
    right: 0;
    width: min(320px, 80vw);
    background: rgba(8, 14, 24, 0.96);
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-radius: 0.75rem;
    padding: 1rem;
    box-shadow: 0 12px 24px rgba(3, 8, 20, 0.6);
    z-index: 50;
    flex-direction: column;
    gap: 0.75rem;
  }
  .web-search-menu::before {
    content: "";
    position: absolute;
    top: -0.25rem;
    left: 0;
    right: 0;
    height: 0.25rem;
  }
  .web-search[data-open="true"] .web-search-menu {
    display: flex;
  }
  .web-search-fields {
    display: grid;
    gap: 0.75rem;
  }
  .web-search-fields label {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.75rem;
    color: #9fb3d8;
  }
  .web-search-fields select,
  .web-search-fields input,
  .web-search-fields textarea {
    background: rgba(12, 19, 34, 0.9);
    border: 1px solid rgba(57, 82, 124, 0.55);
    border-radius: 0.5rem;
    color: #f2f4f8;
    padding: 0.4rem 0.6rem;
    font: inherit;
  }
  .web-search-fields textarea {
    resize: vertical;
    min-height: 3.5rem;
  }
  .web-search-fields select:disabled,
  .web-search-fields input:disabled,
  .web-search-fields textarea:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
