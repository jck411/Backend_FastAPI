<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { renderMarkdown } from "../../utils/markdown";
  import { copyableCode } from "../../actions/copyableCode";
  import type { ToolUsageEntry } from "./toolUsage.types";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";

  const dispatch = createEventDispatcher<{ close: void }>();

  export let open = false;
  export let messageId: string | null = null;
  export let tools: ToolUsageEntry[] = [];

  function handleClose(): void {
    dispatch("close");
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="tool-usage-modal-title"
    modalClass="tool-usage-modal"
    bodyClass="tool-usage-body"
    closeLabel="Close tool usage details"
    on:close={handleClose}
  >
    <svelte:fragment slot="heading">
      <h2 id="tool-usage-modal-title">Tools used</h2>
      {#if messageId}
        <p class="model-settings-subtitle">Message ID: {messageId}</p>
      {/if}
    </svelte:fragment>

    {#if tools.length === 0}
      <p class="status">No tool activity recorded.</p>
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
                  <div class="tool-usage-modal-block" use:copyableCode>
                    {@html renderMarkdown(tool.input)}
                  </div>
                </div>
              {/if}
              {#if tool.result}
                <div class="tool-usage-modal-section">
                  <span class="tool-usage-modal-section-label">Output</span>
                  <div class="tool-usage-modal-block" use:copyableCode>
                    {@html renderMarkdown(tool.result)}
                  </div>
                </div>
              {/if}
              {#if !tool.input && !tool.result}
                <p class="status tool-usage-status">No details provided.</p>
              {/if}
            </details>
          </li>
        {/each}
      </ul>
    {/if}
  </ModelSettingsDialog>
{/if}

<style>
:global(.tool-usage-modal) {
    width: min(520px, 100%);
    max-height: min(75vh, 600px);
  }
:global(.tool-usage-body) {
    padding-bottom: 1.5rem;
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
    line-height: 1.5;
    background: rgba(15, 22, 38, 0.85);
    border-radius: 0.6rem;
    border: 1px solid rgba(67, 91, 136, 0.35);
    padding: 0.75rem 0.85rem;
    color: #dbe9ff;
    overflow-x: auto;
  }
  .tool-usage-modal-block :global(p) {
    margin: 0 0 0.75rem;
  }
  .tool-usage-modal-block :global(p:last-child) {
    margin-bottom: 0;
  }
  .tool-usage-modal-block :global(code) {
    font-family: "Fira Code", "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    background: rgba(28, 38, 60, 0.8);
    border-radius: 0.35rem;
    padding: 0.1rem 0.35rem;
    font-size: 0.8rem;
  }
  .tool-usage-modal-block :global(pre) {
    margin: 0 0 0.85rem;
    background: rgba(13, 20, 34, 0.9);
    border-radius: 0.5rem;
    border: 1px solid rgba(67, 91, 136, 0.35);
    padding: 0.85rem;
    overflow-x: auto;
  }
  .tool-usage-modal-block :global(pre.copy-code-block) {
    position: relative;
    padding-top: 2rem;
  }
  .tool-usage-modal-block :global(pre:last-child) {
    margin-bottom: 0;
  }
  .tool-usage-modal-block :global(.copy-code-button) {
    position: absolute;
    top: 0.55rem;
    right: 0.6rem;
    width: 1.75rem;
    height: 1.75rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 0.45rem;
    background: rgba(8, 14, 24, 0.85);
    color: rgba(222, 234, 255, 0.85);
    cursor: pointer;
    transition:
      color 0.14s ease,
      background 0.14s ease,
      transform 0.14s ease;
  }
  .tool-usage-modal-block :global(.copy-code-button:hover),
  .tool-usage-modal-block :global(.copy-code-button:focus-visible) {
    color: #f1f5ff;
    background: rgba(26, 36, 54, 0.95);
    transform: translateY(-1px);
    outline: none;
  }
  .tool-usage-modal-block :global(.copy-code-button:active) {
    transform: translateY(0);
  }
  .tool-usage-modal-block :global(.copy-code-button.copied) {
    color: #34d399;
  }
  .tool-usage-modal-block :global(.copy-code-button svg) {
    width: 0.95rem;
    height: 0.95rem;
    display: block;
  }
  .tool-usage-modal-block :global(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 0 0 0.75rem;
    font-size: 0.8rem;
  }
  .tool-usage-modal-block :global(table:last-child) {
    margin-bottom: 0;
  }
  .tool-usage-modal-block :global(th),
  .tool-usage-modal-block :global(td) {
    border: 1px solid rgba(67, 91, 136, 0.45);
    padding: 0.45rem 0.6rem;
    text-align: left;
    vertical-align: top;
  }
  .tool-usage-modal-block :global(th) {
    background: rgba(24, 34, 56, 0.85);
    font-weight: 600;
    color: #f1f5ff;
  }
  .tool-usage-modal-block :global(a) {
    color: #7dd3fc;
    text-decoration: underline;
    text-decoration-thickness: 1px;
  }
  .tool-usage-status {
    font-size: 0.78rem;
  }
</style>
