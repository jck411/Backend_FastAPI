<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { ConversationMessage } from "../../stores/chat";
  import { BarChart, Brain, Check, ClipboardCopy, Pencil, RefreshCcw, Trash2, Wrench } from "lucide-svelte";
  import { renderMarkdown } from "../../utils/markdown";
  import { copyableCode } from "../../actions/copyableCode";

  export let message: ConversationMessage;
  export let showToolIndicator = false;
  export let copied = false;
  export let disableDelete = false;

  const dispatch = createEventDispatcher<{
    copy: { message: ConversationMessage };
    openTool: { message: ConversationMessage };
    openReasoning: { message: ConversationMessage };
    openUsage: { id: string };
    edit: { message: ConversationMessage };
    retry: { message: ConversationMessage };
    delete: { message: ConversationMessage };
  }>();

  let hasReasoningSegments = false;

  $: hasReasoningSegments =
    (message.details?.reasoning?.length ?? 0) > 0 || Boolean(message.details?.reasoningStatus);

  function handleCopy(): void {
    dispatch("copy", { message });
  }

  function handleOpenReasoning(): void {
    dispatch("openReasoning", { message });
  }

  function handleOpenTool(): void {
    dispatch("openTool", { message });
  }

  function handleOpenUsage(): void {
    const generationId = message.details?.generationId;
    if (!generationId) {
      return;
    }
    dispatch("openUsage", { id: generationId });
  }

  function handleEdit(): void {
    dispatch("edit", { message });
  }

  function handleRetry(): void {
    dispatch("retry", { message });
  }

  function handleDelete(): void {
    if (disableDelete) {
      return;
    }
    dispatch("delete", { message });
  }
</script>

<article class={`message ${message.role}`}>
  <div class="bubble">
    {#if message.role !== "user"}
      <span class="sender">
        <span class="sender-label">
          {message.role}
          {#if message.role === "assistant"}
            <span class="sender-model">
              {#if message.details?.model}
                <span class="sender-model-text">— {message.details.model}</span>
              {/if}
              {#if hasReasoningSegments}
                <button
                  type="button"
                  class="sender-reasoning-indicator"
                  class:streaming={message.details?.reasoningStatus === "streaming"}
                  aria-label="View reasoning trace"
                  title={message.details?.reasoningStatus === "streaming"
                    ? "Reasoning stream in progress"
                    : "View reasoning trace"}
                  on:click={handleOpenReasoning}
                >
                  <Brain size={14} strokeWidth={1.8} aria-hidden="true" />
                </button>
              {/if}
              {#if showToolIndicator}
                <button
                  type="button"
                  class="sender-tool-indicator"
                  aria-label="View tool usage"
                  title="View tool usage"
                  on:click={handleOpenTool}
                >
                  <Wrench size={14} strokeWidth={1.8} aria-hidden="true" />
                </button>
              {/if}
            </span>
          {/if}
        </span>
      </span>
    {/if}
    <div class="message-content" use:copyableCode>
      {@html renderMarkdown(message.content)}
    </div>
    <div class="message-actions">
      <button
        type="button"
        class="message-action"
        class:copied
        aria-label={copied ? "Message copied" : "Copy message"}
        on:click={handleCopy}
      >
        {#if copied}
          <Check size={16} strokeWidth={1.6} aria-hidden="true" />
        {:else}
          <ClipboardCopy size={16} strokeWidth={1.6} aria-hidden="true" />
        {/if}
      </button>
      {#if message.role === "user"}
        <button type="button" class="message-action" aria-label="Edit message" on:click={handleEdit}>
          <Pencil size={16} strokeWidth={1.6} aria-hidden="true" />
        </button>
      {/if}
      <button type="button" class="message-action" aria-label="Retry message" on:click={handleRetry}>
        <RefreshCcw size={16} strokeWidth={1.6} aria-hidden="true" />
      </button>
      {#if message.role === "assistant" && message.details?.generationId}
        <button
          type="button"
          class="message-action"
          aria-label="View usage details"
          on:click={handleOpenUsage}
        >
          <BarChart size={16} strokeWidth={1.6} aria-hidden="true" />
        </button>
      {/if}
      <button
        type="button"
        class="message-action"
        aria-label="Delete message"
        on:click={handleDelete}
        disabled={disableDelete}
      >
        <Trash2 size={16} strokeWidth={1.6} aria-hidden="true" />
      </button>
    </div>
  </div>
</article>

<style>
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
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .sender-model-text {
    display: inline-block;
  }
  .sender-reasoning-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1rem;
    height: 1rem;
    color: #c084fc;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
  }
  .sender-reasoning-indicator.streaming {
    animation: reasoningPulse 1.25s ease-in-out infinite;
  }
  .sender-reasoning-indicator:hover,
  .sender-reasoning-indicator:focus-visible {
    color: #e9d5ff;
    outline: none;
  }
  .sender-tool-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1rem;
    height: 1rem;
    color: #38bdf8;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
  }
  .sender-tool-indicator:hover,
  .sender-tool-indicator:focus-visible {
    color: #7dd3fc;
    outline: none;
  }
  .message-content {
    line-height: 1.55;
    font-size: 0.95rem;
    color: #e2e8f8;
    overflow-x: auto;
  }
  .message-content :global(p) {
    margin: 0 0 0.85rem;
  }
  .message-content :global(p:last-child) {
    margin-bottom: 0;
  }
  .message-content :global(code) {
    font-family: "Fira Code", "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    background: rgba(24, 34, 56, 0.8);
    border-radius: 0.35rem;
    padding: 0.15rem 0.35rem;
    font-size: 0.85rem;
    word-break: break-word;
  }
  .message-content :global(pre) {
    margin: 0 0 1rem;
    background: rgba(13, 20, 34, 0.9);
    border-radius: 0.65rem;
    border: 1px solid rgba(67, 91, 136, 0.35);
    padding: 1rem 1.1rem;
    overflow-x: auto;
  }
  .message-content :global(pre.copy-code-block) {
    position: relative;
    padding-top: 2.2rem;
  }
  .message-content :global(pre:last-child) {
    margin-bottom: 0;
  }
  .message-content :global(pre code) {
    background: transparent;
    padding: 0;
    font-size: 0.85rem;
    display: block;
  }
  .message-content :global(.copy-code-button) {
    position: absolute;
    top: 0.65rem;
    right: 0.75rem;
    width: 1.85rem;
    height: 1.85rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 0.5rem;
    background: rgba(9, 16, 28, 0.85);
    color: rgba(212, 224, 245, 0.85);
    cursor: pointer;
    transition:
      color 0.14s ease,
      background 0.14s ease,
      transform 0.14s ease;
  }
  .message-content :global(.copy-code-button:hover),
  .message-content :global(.copy-code-button:focus-visible) {
    color: #f8fafc;
    background: rgba(28, 38, 60, 0.95);
    transform: translateY(-1px);
    outline: none;
  }
  .message-content :global(.copy-code-button:active) {
    transform: translateY(0);
  }
  .message-content :global(.copy-code-button.copied) {
    color: #34d399;
  }
  .message-content :global(.copy-code-button svg) {
    width: 1rem;
    height: 1rem;
    display: block;
  }
  .message-content :global(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 0 0 1rem;
    font-size: 0.85rem;
  }
  .message-content :global(table:last-child) {
    margin-bottom: 0;
  }
  .message-content :global(th),
  .message-content :global(td) {
    border: 1px solid rgba(67, 91, 136, 0.45);
    padding: 0.5rem 0.75rem;
    text-align: left;
    vertical-align: top;
  }
  .message-content :global(th) {
    background: rgba(24, 34, 56, 0.85);
    font-weight: 600;
    color: #f8fafc;
  }
  .message-content :global(a) {
    color: #7dd3fc;
    text-decoration: underline;
    text-decoration-thickness: 1px;
  }
  .message-actions {
    position: absolute;
    bottom: -1.6rem;
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
  .message.assistant .message-actions {
    left: 0;
    right: auto;
    justify-content: flex-start;
  }
  .message.user .message-actions {
    right: 0;
    left: auto;
    justify-content: flex-end;
    bottom: -2.1rem;
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
    position: relative;
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
  .message-action.copied {
    color: #34d399;
  }
  .message-action:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
  }
  @keyframes reasoningPulse {
    0% {
      transform: scale(1);
      filter: drop-shadow(0 0 0 rgba(192, 132, 252, 0.35));
    }
    50% {
      transform: scale(1.15);
      filter: drop-shadow(0 0 6px rgba(192, 132, 252, 0.5));
    }
    100% {
      transform: scale(1);
      filter: drop-shadow(0 0 0 rgba(192, 132, 252, 0.35));
    }
  }
</style>
