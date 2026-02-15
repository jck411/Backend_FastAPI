<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { webSearchStore } from "../../chat/webSearchStore";

  export let pwaMode = false;

  const webSearch = webSearchStore;

  let menuOpen = false;
  let closeTimeout: ReturnType<typeof setTimeout> | null = null;
  let wasEnabled = false;
  let menuEl: HTMLElement | null = null;
  let buttonEl: HTMLButtonElement | null = null;
  let containerEl: HTMLElement | null = null;

  function cancelClose(): void {
    if (!closeTimeout) return;
    clearTimeout(closeTimeout);
    closeTimeout = null;
  }

  function openMenu(force = false): void {
    cancelClose();
    if (!force && !webSearch.current.enabled) return;
    menuOpen = true;
    queueMicrotask(() => {
      const first = menuEl?.querySelector<HTMLElement>(
        'select, input, textarea, button, [href], [tabindex]:not([tabindex="-1"])',
      );
      first?.focus();
    });
  }

  function scheduleClose(): void {
    cancelClose();
    closeTimeout = setTimeout(() => {
      if (!menuOpen) return;
      menuOpen = false;
      closeTimeout = null;
    }, 250);
  }

  function closeMenu(): void {
    cancelClose();
    if (!menuOpen) return;
    menuOpen = false;
    buttonEl?.focus();
  }

  function openIfEnabled(): void {
    if (!webSearch.current.enabled) return;
    openMenu();
  }

  function handleButtonClick(): void {
    if (pwaMode) {
      // PWA: toggle on/off, panel follows enabled state
      webSearch.setEnabled(!webSearch.current.enabled);
      return;
    }
    if (webSearch.current.enabled) {
      webSearch.setEnabled(false);
      closeMenu();
    } else {
      webSearch.setEnabled(true);
      openMenu(true);
    }
  }

  function commitEngine(event: Event): void {
    const value = (event.currentTarget as HTMLSelectElement).value;
    webSearch.update({
      engine: value === "native" || value === "exa" ? value : null,
    });
  }

  function commitContext(event: Event): void {
    const value = (event.currentTarget as HTMLSelectElement).value;
    webSearch.update({
      contextSize:
        value === "low" || value === "medium" || value === "high"
          ? value
          : null,
    });
  }

  function commitMaxResults(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    if (input.value === "") {
      webSearch.update({ maxResults: null });
      return;
    }
    let n = Math.trunc(Number(input.value));
    if (!Number.isFinite(n)) return;
    if (n < 1) n = 1;
    if (n > 25) n = 25;
    webSearch.update({ maxResults: n });
  }

  function commitPrompt(event: Event): void {
    const value = (event.currentTarget as HTMLTextAreaElement).value;
    webSearch.update({ searchPrompt: value });
  }

  function handleFocusOut(event: FocusEvent): void {
    const nextTarget = event.relatedTarget as Node | null;
    if (containerEl && nextTarget && containerEl.contains(nextTarget)) {
      return;
    }
    closeMenu();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
      return;
    }
    if (event.key === "Tab" && menuOpen) {
      const focusables = Array.from(
        menuEl?.querySelectorAll<HTMLElement>(
          'select, input, textarea, button, [href], [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  function onDocPointerDown(event: PointerEvent): void {
    if (!menuOpen) return;
    const target = event.target as Node;
    if (menuEl?.contains(target) || buttonEl?.contains(target)) return;
    closeMenu();
  }

  onMount(() => {
    document.addEventListener("pointerdown", onDocPointerDown);
  });

  onDestroy(() => {
    cancelClose();
    document.removeEventListener("pointerdown", onDocPointerDown);
  });

  $: if (!$webSearch.enabled && wasEnabled) {
    closeMenu();
  }

  $: wasEnabled = $webSearch.enabled;
</script>

<div
  class="web-search"
  data-enabled={$webSearch.enabled}
  data-open={pwaMode ? $webSearch.enabled : menuOpen}
  data-pwa={pwaMode}
  role="group"
  aria-label="Web search settings"
  bind:this={containerEl}
>
  {#if pwaMode}
    <!-- PWA: toggle row + collapsible settings dropdown -->
    <div class="pwa-web-search-row">
      <span class="pwa-label">Web Search</span>
      <button
        type="button"
        class="pwa-toggle"
        class:on={$webSearch.enabled}
        on:click={handleButtonClick}
        aria-pressed={$webSearch.enabled}
        aria-label={$webSearch.enabled ? "Turn off web search" : "Turn on web search"}
      >
        <span class="pwa-toggle-knob"></span>
      </button>
    </div>

    {#if $webSearch.enabled}
      <details class="pwa-web-search-details">
        <summary>Search settings</summary>
        <div class="web-search-fields">
          <label>
            <span>Engine</span>
            <select
              class="select-control"
              value={$webSearch.engine ?? ""}
              on:change={commitEngine}
            >
              <option value="">Auto</option>
              <option value="native">Native</option>
              <option value="exa">Exa</option>
            </select>
          </label>

          <label>
            <span>Context</span>
            <select
              class="select-control"
              value={$webSearch.contextSize ?? ""}
              on:change={commitContext}
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
              class="input-control"
              type="number"
              min="1"
              max="25"
              step="1"
              value={$webSearch.maxResults ?? ""}
              on:change={commitMaxResults}
              on:blur={commitMaxResults}
              inputmode="numeric"
              pattern="\\d*"
            />
          </label>

          <label class="prompt">
            <span>Search prompt</span>
            <textarea
              class="textarea-control"
              rows="3"
              value={$webSearch.searchPrompt ?? ""}
              placeholder="Default: A web search was conducted on &#123;today's_date&#125;. Incorporate the following web search results into your response. IMPORTANT: Cite them using markdown links named using the domain of the source."
              on:input={commitPrompt}
            ></textarea>
          </label>
        </div>
      </details>
    {/if}
  {:else}
    <!-- Desktop: original button + floating popup -->
    <button
      bind:this={buttonEl}
      type="button"
      class="btn btn-ghost btn-small web-search-summary"
      aria-haspopup="true"
      aria-expanded={$webSearch.enabled && menuOpen}
      aria-controls="webSearchMenu"
      on:click={handleButtonClick}
      on:mouseenter={openIfEnabled}
      on:focus={openIfEnabled}
      on:mouseleave={scheduleClose}
      on:keydown={handleKeydown}
    >
      <span>Web search</span>
      <span
        class="status"
        data-enabled={$webSearch.enabled}
        aria-label={$webSearch.enabled ? "Web search on" : "Web search off"}
      >
        {$webSearch.enabled ? "On" : "Off"}
      </span>
    </button>

    {#if menuOpen && $webSearch.enabled}
      <div
        class="web-search-menu"
        id="webSearchMenu"
        role="dialog"
        tabindex="-1"
        bind:this={menuEl}
        on:mouseenter={cancelClose}
        on:mouseleave={scheduleClose}
        on:focusin={cancelClose}
        on:focusout={handleFocusOut}
        on:keydown={handleKeydown}
      >
        <div class="web-search-fields">
          <label>
            <span>Engine</span>
            <select
              class="select-control"
              value={$webSearch.engine ?? ""}
              disabled={!$webSearch.enabled}
              on:change={commitEngine}
            >
              <option value="">Auto</option>
              <option value="native">Native</option>
              <option value="exa">Exa</option>
            </select>
          </label>

          <label>
            <span>Context</span>
            <select
              class="select-control"
              value={$webSearch.contextSize ?? ""}
              disabled={!$webSearch.enabled}
              on:change={commitContext}
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
              class="input-control"
              type="number"
              min="1"
              max="25"
              step="1"
              value={$webSearch.maxResults ?? ""}
              disabled={!$webSearch.enabled}
              on:change={commitMaxResults}
              on:blur={commitMaxResults}
              inputmode="numeric"
              pattern="\\d*"
            />
          </label>

          <label class="prompt">
            <span>Search prompt</span>
            <textarea
              class="textarea-control"
              rows="5"
              value={$webSearch.searchPrompt ?? ""}
              disabled={!$webSearch.enabled}
              placeholder="Default: A web search was conducted on &#123;today's_date&#125;. Incorporate the following web search results into your response. IMPORTANT: Cite them using markdown links named using the domain of the source."
              on:input={commitPrompt}
            ></textarea>
          </label>
        </div>
      </div>
    {/if}
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
    transform: none;
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
  .web-search-fields textarea {
    resize: vertical;
    min-height: 3.5rem;
  }

  .web-search *:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }
  .web-search *:focus {
    outline: none;
  }

  @media (max-width: 640px) {
    .web-search-menu {
      right: auto;
      transform: none;
      width: min(320px, calc(100vw - 2rem));
      left: max(0px, calc((100% - min(320px, calc(100vw - 2rem))) / 2));
    }
  }

  @media (max-width: 480px) {
    .web-search-menu {
      width: calc(100vw - 1.5rem);
      left: max(0px, calc((100% - calc(100vw - 1.5rem)) / 2));
    }
  }

  /* PWA mode: inline toggle + details dropdown */
  .web-search[data-pwa="true"] {
    display: flex;
    flex-direction: column;
    width: 100%;
    gap: 0;
  }
  .pwa-web-search-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0.55rem 0.75rem;
    border: 1px solid rgba(37, 49, 77, 0.6);
    border-radius: 0.5rem;
    background: rgba(9, 14, 26, 0.6);
    color: #c8d6ef;
    font-size: 0.85rem;
  }
  .web-search[data-pwa="true"][data-enabled="true"] .pwa-web-search-row {
    border-radius: 0.5rem 0.5rem 0 0;
    border-bottom-color: transparent;
  }
  .pwa-label {
    font-weight: 500;
  }
  .pwa-toggle {
    position: relative;
    width: 2.6rem;
    height: 1.4rem;
    border-radius: 999px;
    border: 1px solid rgba(62, 90, 140, 0.6);
    background: rgba(30, 40, 60, 0.8);
    cursor: pointer;
    padding: 0;
    transition: background 0.2s ease, border-color 0.2s ease;
  }
  .pwa-toggle.on {
    background: rgba(56, 189, 248, 0.25);
    border-color: rgba(56, 189, 248, 0.5);
  }
  .pwa-toggle-knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 1rem;
    height: 1rem;
    border-radius: 999px;
    background: #9fb3d8;
    transition: transform 0.2s ease, background 0.2s ease;
  }
  .pwa-toggle.on .pwa-toggle-knob {
    transform: translateX(1.2rem);
    background: #38bdf8;
  }
  .pwa-web-search-details {
    width: 100%;
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-top: none;
    border-radius: 0 0 0.5rem 0.5rem;
    background: rgba(8, 14, 24, 0.7);
    overflow: hidden;
  }
  .pwa-web-search-details summary {
    padding: 0.5rem 0.75rem;
    font-size: 0.78rem;
    color: #7da0c9;
    cursor: pointer;
    user-select: none;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .pwa-web-search-details summary::-webkit-details-marker {
    display: none;
  }
  .pwa-web-search-details summary::before {
    content: "▸";
    display: inline-block;
    transition: transform 0.15s ease;
    font-size: 0.7rem;
  }
  .pwa-web-search-details[open] summary::before {
    transform: rotate(90deg);
  }
  .pwa-web-search-details .web-search-fields {
    padding: 0.5rem 0.75rem 0.75rem;
  }
  .web-search[data-pwa="true"] .web-search-summary {
    display: none;
  }
  .web-search[data-pwa="true"] .web-search-menu {
    display: none;
  }
</style>
