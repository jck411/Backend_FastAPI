<script lang="ts">
  import { afterUpdate, createEventDispatcher } from "svelte";
  import type { ConversationMessage } from "../../stores/chat";
  // Use Lucide icons for consistent, theme-friendly line icons
  import {
    BarChart,
    ClipboardCopy,
    Pencil,
    RefreshCcw,
    Trash2,
  } from "lucide-svelte";

  export let messages: ConversationMessage[] = [];

  let container: HTMLElement | null = null;

  const dispatch = createEventDispatcher<{
    openGenerationDetails: { id: string };
  }>();

  afterUpdate(() => {
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  });

  function handleUsageClick(id: string | null | undefined): void {
    if (!id) return;
    dispatch("openGenerationDetails", { id });
  }
</script>

<section class="conversation" bind:this={container} aria-live="polite">
  {#each messages as message (message.id)}
    <article class={`message ${message.role}`}>
      <div class="bubble">
        {#if message.role !== "user"}
          <span class="sender">
            <span class="sender-label">
              {message.role}
              {#if message.role === "assistant" && message.details?.model}
                <span class="sender-model"> — {message.details.model}</span>
              {/if}
            </span>
            {#if message.role === "assistant" && message.details?.generationId}
              <button
                type="button"
                class="sender-link"
                on:click={() => handleUsageClick(message.details?.generationId)}
              >
                View usage
              </button>
            {/if}
          </span>
        {/if}
        <p>{message.content}</p>
        {#if message.pending}
          <span class="pending">…</span>
        {/if}
        <div class="message-actions">
          <button
            type="button"
            class="message-action"
            aria-label="Copy message"
          >
            <ClipboardCopy size={16} strokeWidth={1.6} aria-hidden="true" />
          </button>
          <button
            type="button"
            class="message-action"
            aria-label="Edit message"
          >
            <Pencil size={16} strokeWidth={1.6} aria-hidden="true" />
          </button>
          <button
            type="button"
            class="message-action"
            aria-label="Retry message"
          >
            <RefreshCcw size={16} strokeWidth={1.6} aria-hidden="true" />
          </button>
          <button
            type="button"
            class="message-action"
            aria-label="View details"
          >
            <BarChart size={16} strokeWidth={1.6} aria-hidden="true" />
          </button>
          <button
            type="button"
            class="message-action"
            aria-label="Delete message"
          >
            <Trash2 size={16} strokeWidth={1.6} aria-hidden="true" />
          </button>
        </div>
      </div>
    </article>
  {/each}
</section>

<style>
  .conversation {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 2rem 0;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    scroll-padding-top: 4rem;
    scroll-padding-bottom: 4rem;
    scrollbar-gutter: stable;
  }
  .conversation > * {
    padding: 0 2rem;
    max-width: min(800px, 100%);
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }
  .message {
    display: flex;
  }
  .message.user {
    justify-content: flex-end;
  }
  .message.assistant {
    justify-content: flex-start;
  }
  .bubble {
    max-width: 75%;
    padding: 1rem 1.5rem;
    border-radius: 0.95rem;
    background: rgba(18, 26, 46, 0.85);
    border: 1px solid rgba(58, 77, 120, 0.38);
    position: relative;
  }
  .message.user .bubble {
    background: rgba(38, 50, 88, 0.78);
  }
  .message.assistant .bubble {
    background: transparent;
    border: none;
    padding: 0.5rem 0;
  }
  .sender {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: #7b87a1;
  }
  .sender-label {
    text-transform: uppercase;
  }
  .sender-label .sender-model {
    text-transform: none;
    font-weight: 500;
  }
  .sender-link {
    text-transform: none;
    background: none;
    border: none;
    color: #38bdf8;
    font: inherit;
    padding: 0;
    cursor: pointer;
  }
  .sender-link:hover,
  .sender-link:focus {
    text-decoration: underline;
    color: #7dd3fc;
  }
  .bubble p {
    margin: 0;
    white-space: pre-wrap;
    line-height: 1.55;
  }
  .pending {
    position: absolute;
    bottom: 0.5rem;
    right: 0.85rem;
    font-size: 1.25rem;
    color: #38bdf8;
  }
  .message-actions {
    position: absolute;
    bottom: -1.4rem;
    display: flex;
    gap: 0.35rem;
    padding: 0.1rem 0.2rem;
    background: transparent;
    border: none;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s ease;
    z-index: 5;
  }
  .message:hover .message-actions,
  .message:focus-within .message-actions {
    opacity: 1;
    pointer-events: auto;
  }
  /* Position per role: left for assistant, right for user */
  .message.assistant .message-actions {
    left: 0.25rem;
    right: auto;
    justify-content: flex-start;
  }
  .message.user .message-actions {
    right: 0.25rem;
    left: auto;
    justify-content: flex-end;
    bottom: -1.9rem;
  }
  .message-action {
    width: 1.8rem;
    height: 1.8rem;
    border-radius: 0.5rem;
    border: none;
    background: transparent;
    color: rgba(212, 224, 245, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
    transition:
      color 0.12s ease,
      transform 0.12s ease;
  }
  .message-action:hover,
  .message-action:focus-visible {
    color: #f8fafc;
    transform: translateY(-1px);
    outline: none;
  }
  .message-action:active {
    transform: translateY(0);
  }
  /* Icon rendering handled by lucide-svelte props; buttons inherit color */
</style>
