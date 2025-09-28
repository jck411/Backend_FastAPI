<script lang="ts">
  import { afterUpdate, createEventDispatcher } from "svelte";

  export interface ToolUsageEntry {
    id: string;
    name: string;
    status: string | null;
    input: string | null;
    result: string | null;
  }

  const dispatch = createEventDispatcher<{ close: void }>();

  export let open = false;
  export let messageId: string | null = null;
  export let tools: ToolUsageEntry[] = [];

  let dialogEl: HTMLElement | null = null;

  afterUpdate(() => {
    if (open && dialogEl) {
      dialogEl.focus();
    }
  });

  function handleClose(): void {
    dispatch("close");
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      handleClose();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="tool-usage-modal-layer">
    <button
      type="button"
      class="tool-usage-modal-backdrop"
      aria-label="Close tool usage details"
      on:click={handleClose}
    ></button>
    <div
      class="tool-usage-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tool-usage-modal-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="tool-usage-modal-header">
        <div>
          <h2 id="tool-usage-modal-title">Tools used</h2>
          {#if messageId}
            <p class="tool-usage-modal-subtitle">Message ID: {messageId}</p>
          {/if}
        </div>
        <button
          type="button"
          class="modal-close"
          on:click={handleClose}
          aria-label="Close tool usage details"
        >
          Close
        </button>
      </header>
      <section class="tool-usage-modal-body">
        {#if tools.length === 0}
          <p class="tool-usage-modal-status">No tool activity recorded.</p>
        {:else}
          <ul class="tool-usage-modal-list">
            {#each tools as tool (tool.id)}
              <li class="tool-usage-modal-item">
                <div class="tool-usage-modal-item-header">
                  <span class="tool-usage-modal-name">{tool.name}</span>
                  {#if tool.status}
                    <span class="tool-usage-modal-status-pill">{tool.status}</span>
                  {/if}
                </div>
                <details class="tool-usage-modal-details">
                  <summary class="tool-usage-modal-summary">Show input &amp; output</summary>
                  {#if tool.input}
                    <div class="tool-usage-modal-section">
                      <span class="tool-usage-modal-section-label">Input</span>
                      <pre class="tool-usage-modal-block">{tool.input}</pre>
                    </div>
                  {/if}
                  {#if tool.result}
                    <div class="tool-usage-modal-section">
                      <span class="tool-usage-modal-section-label">Output</span>
                      <pre class="tool-usage-modal-block">{tool.result}</pre>
                    </div>
                  {/if}
                  {#if !tool.input && !tool.result}
                    <p class="tool-usage-modal-status">No details provided.</p>
                  {/if}
                </details>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
  </div>
{/if}

<style>
  .tool-usage-modal-layer {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    z-index: 130;
  }
  .tool-usage-modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(4, 8, 20, 0.6);
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
  }
  .tool-usage-modal-backdrop:focus-visible {
    outline: 2px solid #38bdf8;
  }
  .tool-usage-modal {
    position: relative;
    width: min(480px, 100%);
    max-height: min(75vh, 600px);
    background: rgba(10, 16, 28, 0.95);
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-radius: 1rem;
    box-shadow: 0 18px 48px rgba(3, 8, 20, 0.55);
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1;
  }
  .tool-usage-modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 1.25rem 1.5rem 1rem;
    border-bottom: 1px solid rgba(67, 91, 136, 0.45);
  }
  .tool-usage-modal-header h2 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }
  .tool-usage-modal-subtitle {
    margin: 0.35rem 0 0;
    font-size: 0.75rem;
    color: #8ea7d2;
    word-break: break-all;
  }
  .modal-close {
    background: none;
    border: 1px solid rgba(71, 99, 150, 0.6);
    border-radius: 999px;
    color: #f3f5ff;
    padding: 0.35rem 0.9rem;
    cursor: pointer;
    font-size: 0.75rem;
  }
  .modal-close:hover,
  .modal-close:focus-visible {
    border-color: #38bdf8;
    color: #38bdf8;
    outline: none;
  }
  .tool-usage-modal-body {
    padding: 1.25rem 1.5rem 1.5rem;
    overflow-y: auto;
  }
  .tool-usage-modal-status {
    margin: 0;
    font-size: 0.9rem;
    color: #9fb3d8;
  }
  .tool-usage-modal-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .tool-usage-modal-item {
    border: 1px solid rgba(67, 91, 136, 0.4);
    border-radius: 0.75rem;
    background: rgba(9, 14, 26, 0.6);
    padding: 0.9rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .tool-usage-modal-item-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }
  .tool-usage-modal-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #f3f5ff;
  }
  .tool-usage-modal-status-pill {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.2rem 0.45rem;
    border-radius: 999px;
    background: rgba(56, 189, 248, 0.12);
    color: #7dd3fc;
    border: 1px solid rgba(56, 189, 248, 0.25);
  }
  .tool-usage-modal-details {
    border-top: 1px solid rgba(67, 91, 136, 0.35);
    padding-top: 0.5rem;
  }
  .tool-usage-modal-summary {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #94addb;
  }
  .tool-usage-modal-summary::-webkit-details-marker {
    display: none;
  }
  .tool-usage-modal-summary::before {
    content: '\25B8';
    transition: transform 0.2s ease;
    font-size: 0.75rem;
  }
  .tool-usage-modal-details[open] .tool-usage-modal-summary::before {
    transform: rotate(90deg);
  }
  .tool-usage-modal-section {
    margin-top: 0.65rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .tool-usage-modal-section-label {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #7b92c4;
  }
  .tool-usage-modal-block {
    margin: 0;
    font-size: 0.85rem;
    line-height: 1.4;
    white-space: pre-wrap;
    background: rgba(15, 22, 38, 0.85);
    border-radius: 0.6rem;
    border: 1px solid rgba(67, 91, 136, 0.35);
    padding: 0.65rem;
    color: #dbe9ff;
    overflow-x: auto;
  }
</style>
