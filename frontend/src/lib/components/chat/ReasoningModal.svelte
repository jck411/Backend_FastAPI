<script lang="ts">
  import { afterUpdate, createEventDispatcher } from "svelte";
  import type { ReasoningSegment, ReasoningStatus } from "../../chat/reasoning";

  const dispatch = createEventDispatcher<{ close: void }>();

  export let open = false;
  export let messageId: string | null = null;
  export let segments: ReasoningSegment[] = [];
  export let status: ReasoningStatus | null = null;

  let dialogEl: HTMLElement | null = null;
  let bodyEl: HTMLElement | null = null;
  let reasoningText = "";
  const SCROLL_LOCK_THRESHOLD = 12;
  let autoScroll = true;
  let wasOpen = false;

  function joinReasoningSegments(entries: ReasoningSegment[]): string {
    if (!entries || entries.length === 0) {
      return "";
    }
    let output = "";
    let previousType: string | undefined;

    for (const segment of entries) {
      if (!segment || typeof segment.text !== "string" || segment.text.length === 0) {
        continue;
      }
      const currentText = segment.text;
      const typeChanged = previousType && segment.type && previousType !== segment.type;

      if (typeChanged) {
        if (!output.endsWith("\n")) {
          output += "\n";
        }
        output += "\n";
      }

      const needsSpaceBefore =
        output.length > 0 &&
        !output.endsWith(" ") &&
        !output.endsWith("\n") &&
        !output.endsWith("\t") &&
        !output.endsWith("(") &&
        !output.endsWith("[") &&
        !output.endsWith("{") &&
        !output.endsWith("/") &&
        !output.endsWith("'") &&
        !output.endsWith("’") &&
        !/^[\s,.!?;:)/\]\}'"›»]/u.test(currentText) &&
        currentText[0] !== "'" &&
        currentText[0] !== "’";

      if (needsSpaceBefore) {
        output += " ";
      }

      output += currentText;
      previousType = segment.type ?? previousType;
    }

    return output;
  }

  afterUpdate(() => {
    if (open && !wasOpen) {
      autoScroll = true;
    }
    wasOpen = open;

    if (open && dialogEl) {
      dialogEl.focus();
    }
    if (open && bodyEl && status === "streaming" && autoScroll) {
      bodyEl.scrollTop = bodyEl.scrollHeight;
    }
  });

  function handleBodyScroll(): void {
    if (!bodyEl) {
      return;
    }
    const { scrollTop, scrollHeight, clientHeight } = bodyEl;
    const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
    autoScroll = distanceFromBottom <= SCROLL_LOCK_THRESHOLD;
  }

  $: reasoningText = joinReasoningSegments(segments);

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
  <div class="reasoning-modal-layer">
    <button
      type="button"
      class="reasoning-modal-backdrop"
      aria-label="Close reasoning details"
      on:click={handleClose}
    ></button>
    <div
      class="reasoning-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="reasoning-modal-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="reasoning-modal-header">
        <div>
          <h2 id="reasoning-modal-title">Reasoning trace</h2>
          {#if messageId}
            <p class="reasoning-modal-subtitle">Message ID: {messageId}</p>
          {/if}
        </div>
        <div class="reasoning-modal-actions">
          {#if status}
            <span class={`reasoning-status ${status}`} aria-live="polite">
              <span class="reasoning-status-indicator" aria-hidden="true"></span>
              {status === "streaming" ? "Streaming" : "Complete"}
            </span>
          {/if}
          <button
            type="button"
            class="modal-close"
            on:click={handleClose}
            aria-label="Close reasoning details"
          >
            Close
          </button>
        </div>
      </header>
      <section class="reasoning-modal-body" bind:this={bodyEl} on:scroll={handleBodyScroll}>
        {#if reasoningText.length === 0}
          <p class="reasoning-modal-status">No reasoning data received yet.</p>
        {:else}
          <pre class="reasoning-modal-text">{reasoningText}</pre>
        {/if}
      </section>
    </div>
  </div>
{/if}

<style>
  .reasoning-modal-layer {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    z-index: 140;
  }
  .reasoning-modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(4, 8, 20, 0.6);
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
  }
  .reasoning-modal-backdrop:focus-visible {
    outline: 2px solid #38bdf8;
  }
  .reasoning-modal {
    position: relative;
    width: min(520px, 100%);
    max-height: min(75vh, 640px);
    background: rgba(10, 16, 28, 0.95);
    border: 1px solid rgba(78, 54, 128, 0.4);
    border-radius: 1rem;
    box-shadow: 0 18px 48px rgba(3, 8, 20, 0.55);
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1;
  }
  .reasoning-modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1.25rem;
    padding: 1.25rem 1.5rem 1rem;
    border-bottom: 1px solid rgba(78, 54, 128, 0.35);
  }
  .reasoning-modal-header h2 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }
  .reasoning-modal-subtitle {
    margin: 0.35rem 0 0;
    font-size: 0.75rem;
    color: #9f8ed2;
    word-break: break-all;
  }
  .reasoning-modal-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .modal-close {
    background: none;
    border: 1px solid rgba(124, 58, 237, 0.4);
    border-radius: 999px;
    color: #f3f5ff;
    padding: 0.35rem 0.9rem;
    cursor: pointer;
    font-size: 0.75rem;
  }
  .modal-close:hover,
  .modal-close:focus-visible {
    border-color: #c084fc;
    color: #c084fc;
    outline: none;
  }
  .reasoning-status {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.025em;
    text-transform: uppercase;
    padding: 0.25rem 0.65rem;
    border-radius: 999px;
    border: 1px solid rgba(192, 132, 252, 0.35);
    color: #e9d5ff;
    background: rgba(124, 58, 237, 0.12);
  }
  .reasoning-status.streaming {
    animation: reasoningStatusPulse 1.4s ease-in-out infinite;
  }
  .reasoning-status-indicator {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    background: #c084fc;
    position: relative;
  }
  .reasoning-modal-body {
    padding: 1.25rem 1.5rem 1.5rem;
    overflow-y: auto;
  }
  .reasoning-modal-status {
    margin: 0;
    font-size: 0.9rem;
    color: #b8a6e3;
  }
  .reasoning-modal-text {
    margin: 0;
    font-size: 0.88rem;
    line-height: 1.5;
    white-space: pre-wrap;
    background: rgba(24, 32, 52, 0.85);
    border-radius: 0.75rem;
    border: 1px solid rgba(99, 102, 241, 0.3);
    padding: 0.85rem 1rem;
    color: #f3f5ff;
    overflow-x: auto;
  }
  @keyframes reasoningStatusPulse {
    0% {
      box-shadow: 0 0 0 0 rgba(192, 132, 252, 0.45);
    }
    70% {
      box-shadow: 0 0 0 10px rgba(192, 132, 252, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(192, 132, 252, 0);
    }
  }
</style>
