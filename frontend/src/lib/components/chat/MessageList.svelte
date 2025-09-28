<script lang="ts">
  import { afterUpdate, createEventDispatcher, onDestroy } from "svelte";
  import type { ConversationMessage, ConversationRole } from "../../stores/chat";
  // Use Lucide icons for consistent, theme-friendly line icons
  import {
    BarChart,
    Check,
    ClipboardCopy,
    Pencil,
    RefreshCcw,
    Trash2,
    Wrench,
  } from "lucide-svelte";
  import ToolUsageModal from "./ToolUsageModal.svelte";
  import type { ToolUsageEntry } from "./toolUsage.types";

  export let messages: ConversationMessage[] = [];

  let container: HTMLElement | null = null;
  let copiedMessageId: string | null = null;
  let copyResetTimeout: ReturnType<typeof setTimeout> | null = null;
  let visibleMessages: ConversationMessage[] = [];
  let assistantToolUsage: Record<string, boolean> = {};
  let messageIndexMap: Record<string, number> = {};
  let toolModalOpen = false;
  let toolModalEntries: ToolUsageEntry[] = [];
  let toolModalMessageId: string | null = null;
  const TOOL_ROLE: ConversationRole = "tool";
  let suppressNextScroll = false;

  const dispatch = createEventDispatcher<{
    openGenerationDetails: { id: string };
  }>();

  afterUpdate(() => {
    if (!container) {
      return;
    }
    if (suppressNextScroll) {
      suppressNextScroll = false;
      return;
    }
    container.scrollTop = container.scrollHeight;
  });

  function handleUsageClick(id: string | null | undefined): void {
    if (!id) return;
    dispatch("openGenerationDetails", { id });
  }

  async function handleCopyMessage(message: ConversationMessage): Promise<void> {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch (error) {
      console.error("Failed to copy message", error);
      return;
    }

    copiedMessageId = message.id;
    suppressNextScroll = true;
    if (copyResetTimeout) {
      clearTimeout(copyResetTimeout);
    }
    copyResetTimeout = setTimeout(() => {
      suppressNextScroll = true;
      copiedMessageId = null;
      copyResetTimeout = null;
    }, 2000);
  }

  onDestroy(() => {
    if (copyResetTimeout) {
      clearTimeout(copyResetTimeout);
    }
  });

  $: {
    const nextVisible: ConversationMessage[] = [];
    const toolUsage: Record<string, boolean> = {};
    const indexMap: Record<string, number> = {};

    for (let index = 0; index < messages.length; index += 1) {
      const message = messages[index];
      indexMap[message.id] = index;

      if (message.role === "assistant") {
        const toolCalls = message.details?.toolCalls;
        const hasMetadataToolCalls = Array.isArray(toolCalls) && toolCalls.length > 0;
        let usedTool = hasMetadataToolCalls;

        const nextMessage = messages[index + 1];
        if (nextMessage?.role === TOOL_ROLE) {
          usedTool = true;
        }

        toolUsage[message.id] = usedTool;
      }

      if (message.role !== TOOL_ROLE) {
        nextVisible.push(message);
      }
    }

    visibleMessages = nextVisible;
    assistantToolUsage = toolUsage;
    messageIndexMap = indexMap;
  }

  function isToolMessage(
    value: ConversationMessage | undefined,
  ): value is ConversationMessage {
    return value?.role === TOOL_ROLE;
  }

  function extractCallName(call: Record<string, unknown> | null | undefined): string | null {
    if (!call) {
      return null;
    }
    const name = call["name"];
    if (typeof name === "string" && name.trim().length > 0) {
      return name;
    }
    const fn = call["function"];
    if (fn && typeof fn === "object") {
      const functionName = (fn as Record<string, unknown>).name;
      if (typeof functionName === "string" && functionName.trim().length > 0) {
        return functionName;
      }
    }
    return null;
  }

  function extractCallResult(call: Record<string, unknown> | null | undefined): string | null {
    if (!call) {
      return null;
    }
    const resultValue = call["result"];
    if (typeof resultValue === "string") {
      return resultValue;
    }
    if (resultValue && typeof resultValue === "object") {
      try {
        return JSON.stringify(resultValue, null, 2);
      } catch (error) {
        console.warn("Failed to stringify tool result", error);
      }
    }
    const fn = call["function"];
    if (fn && typeof fn === "object") {
      const args = (fn as Record<string, unknown>)["arguments"];
      if (typeof args === "string") {
        return args;
      }
      if (args && typeof args === "object") {
        try {
          return JSON.stringify(args, null, 2);
        } catch (error) {
          console.warn("Failed to stringify tool arguments", error);
        }
      }
    }
    return null;
  }

  function extractCallArguments(call: Record<string, unknown> | null | undefined): string | null {
    if (!call) {
      return null;
    }

    const directArgs = call["arguments"];
    const normalizedArgs = normalizeArgumentValue(directArgs);
    if (normalizedArgs) {
      return normalizedArgs;
    }

    const fn = call["function"];
    if (fn && typeof fn === "object") {
      const functionArgs = normalizeArgumentValue((fn as Record<string, unknown>)["arguments"]);
      if (functionArgs) {
        return functionArgs;
      }
    }

    return null;
  }

  function normalizeArgumentValue(value: unknown): string | null {
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (!trimmed) {
        return null;
      }
      try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed === "string") {
          return parsed;
        }
        return JSON.stringify(parsed, null, 2);
      } catch (error) {
        return trimmed;
      }
    }

    if (value && typeof value === "object") {
      try {
        return JSON.stringify(value, null, 2);
      } catch (error) {
        console.warn("Failed to stringify tool arguments", error, value);
      }
    }

    return null;
  }

  function deriveToolUsageEntries(messageId: string): ToolUsageEntry[] {
    const index = messageIndexMap[messageId];
    if (typeof index !== "number") {
      return [];
    }

    const assistantMessage = messages[index];
    if (!assistantMessage || assistantMessage.role !== "assistant") {
      return [];
    }

    const entries: ToolUsageEntry[] = [];
    const metadataCalls = Array.isArray(assistantMessage.details?.toolCalls)
      ? (assistantMessage.details?.toolCalls as Array<Record<string, unknown>>)
      : [];

    let lookaheadIndex = index + 1;
    while (isToolMessage(messages[lookaheadIndex])) {
      const toolMessage = messages[lookaheadIndex];
      const details = toolMessage.details ?? {};
      const metadataCall = metadataCalls[entries.length];
      const nameFromDetails = typeof details?.toolName === "string" ? details.toolName : null;
      const name = nameFromDetails ?? extractCallName(metadataCall) ?? "Tool";
      const status = typeof details?.toolStatus === "string" ? details.toolStatus : null;
      const resultFromDetails =
        typeof details?.toolResult === "string" ? details.toolResult : toolMessage.content ?? null;
      const result = resultFromDetails ?? extractCallResult(metadataCall);
      const input = extractCallArguments(metadataCall);

      entries.push({
        id: toolMessage.id,
        name,
        status,
        input,
        result,
      });

      lookaheadIndex += 1;
    }

    if (entries.length === 0 && metadataCalls.length > 0) {
      metadataCalls.forEach((call, callIndex) => {
        entries.push({
          id: `${assistantMessage.id}-metadata-${callIndex}`,
          name: extractCallName(call) ?? `Tool ${callIndex + 1}`,
          status: null,
          input: extractCallArguments(call),
          result: extractCallResult(call),
        });
      });
    } else if (entries.length > 0 && metadataCalls.length > 0) {
      entries.forEach((entry, entryIndex) => {
        const metadataCall = metadataCalls[entryIndex];
        if (!metadataCall) {
          return;
        }
        if (!entry.name || entry.name === "Tool") {
          entry.name = extractCallName(metadataCall) ?? entry.name;
        }
        if (!entry.input) {
          entry.input = extractCallArguments(metadataCall);
        }
        if (!entry.result) {
          entry.result = extractCallResult(metadataCall);
        }
      });
    }

    return entries;
  }

  function handleOpenToolModal(message: ConversationMessage): void {
    toolModalEntries = deriveToolUsageEntries(message.id);
    toolModalMessageId = message.id;
    toolModalOpen = true;
  }

  function handleCloseToolModal(): void {
    toolModalOpen = false;
    toolModalEntries = [];
    toolModalMessageId = null;
  }
</script>

<section class="conversation" bind:this={container} aria-live="polite">
  {#each visibleMessages as message (message.id)}
    <article class={`message ${message.role}`}>
      <div class="bubble">
        {#if message.role !== "user"}
          <span class="sender">
            <span class="sender-label">
              {message.role}
              {#if message.role === "assistant" && message.details?.model}
                <span class="sender-model">
                  — {message.details.model}
                  {#if assistantToolUsage[message.id]}
                    <button
                      type="button"
                      class="sender-tool-indicator"
                      aria-label="View tool usage"
                      title="View tool usage"
                      on:click={() => handleOpenToolModal(message)}
                    >
                      <Wrench size={14} strokeWidth={1.8} aria-hidden="true" />
                    </button>
                  {/if}
                </span>
              {/if}
            </span>
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
            class:copied={copiedMessageId === message.id}
            aria-label={copiedMessageId === message.id ? "Message copied" : "Copy message"}
            on:click={() => handleCopyMessage(message)}
          >
            {#if copiedMessageId === message.id}
              <Check size={16} strokeWidth={1.6} aria-hidden="true" />
            {:else}
              <ClipboardCopy size={16} strokeWidth={1.6} aria-hidden="true" />
            {/if}
          </button>
          {#if message.role === "user"}
            <button
              type="button"
              class="message-action"
              aria-label="Edit message"
            >
              <Pencil size={16} strokeWidth={1.6} aria-hidden="true" />
            </button>
          {/if}
          <button
            type="button"
            class="message-action"
            aria-label="Retry message"
          >
            <RefreshCcw size={16} strokeWidth={1.6} aria-hidden="true" />
          </button>
          {#if message.role === "assistant" && message.details?.generationId}
            <button
              type="button"
              class="message-action"
              aria-label="View usage details"
              on:click={() => handleUsageClick(message.details?.generationId)}
            >
              <BarChart size={16} strokeWidth={1.6} aria-hidden="true" />
            </button>
          {/if}
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

<ToolUsageModal
  open={toolModalOpen}
  messageId={toolModalMessageId}
  tools={toolModalEntries}
  on:close={handleCloseToolModal}
/>

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
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
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
  /* Position per role: left for assistant, right for user */
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
  /* Icon rendering handled by lucide-svelte props; buttons inherit color */
</style>
