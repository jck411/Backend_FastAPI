<script lang="ts">
  import { afterUpdate, createEventDispatcher, onDestroy } from "svelte";
  import type {
    ConversationMessage,
    ConversationRole,
    ReasoningSegment,
    ReasoningStatus,
  } from "../../stores/chat";
  import ToolUsageModal from "./ToolUsageModal.svelte";
  import ReasoningModal from "./ReasoningModal.svelte";
  import type { ToolUsageEntry } from "./toolUsage.types";
  import MessageItem from "./MessageItem.svelte";
  import { computeMessagePresentation, deriveToolUsageEntries } from "./toolUsage.helpers";

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
  let reasoningModalOpen = false;
  let reasoningModalSegments: ReasoningSegment[] = [];
  let reasoningModalMessageId: string | null = null;
  let reasoningModalStatus: ReasoningStatus | null = null;
  const TOOL_ROLE: ConversationRole = "tool";
  let suppressNextScroll = false;
  const SCROLL_LOCK_THRESHOLD = 12;
  let autoScroll = true;

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
    if (!autoScroll) {
      return;
    }
    container.scrollTop = container.scrollHeight;
  });

  function handleScroll(): void {
    if (!container) {
      return;
    }
    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
    autoScroll = distanceFromBottom <= SCROLL_LOCK_THRESHOLD;
  }

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
    const presentation = computeMessagePresentation(messages, TOOL_ROLE);
    visibleMessages = presentation.visibleMessages;
    assistantToolUsage = presentation.assistantToolUsage;
    messageIndexMap = presentation.messageIndexMap;
  }

  function handleOpenToolModal(message: ConversationMessage): void {
    toolModalEntries = deriveToolUsageEntries(messages, messageIndexMap, message.id, TOOL_ROLE);
    toolModalMessageId = message.id;
    toolModalOpen = true;
  }

  function handleCloseToolModal(): void {
    toolModalOpen = false;
    toolModalEntries = [];
    toolModalMessageId = null;
  }

  function handleOpenReasoningModal(message: ConversationMessage): void {
    reasoningModalMessageId = message.id;
    reasoningModalSegments = message.details?.reasoning ?? [];
    reasoningModalStatus = message.details?.reasoningStatus ?? null;
    reasoningModalOpen = true;
  }

  function handleCloseReasoningModal(): void {
    reasoningModalOpen = false;
    reasoningModalMessageId = null;
    reasoningModalSegments = [];
    reasoningModalStatus = null;
  }

  $: if (reasoningModalOpen && reasoningModalMessageId) {
    const currentMessage = messages.find((msg) => msg.id === reasoningModalMessageId);
    reasoningModalSegments = currentMessage?.details?.reasoning ?? [];
    reasoningModalStatus = currentMessage?.details?.reasoningStatus ?? null;
  }
</script>

<section class="conversation" bind:this={container} aria-live="polite" on:scroll={handleScroll}>
  {#each visibleMessages as message (message.id)}
    <div class="conversation-item">
      <MessageItem
        {message}
        showToolIndicator={assistantToolUsage[message.id]}
        copied={copiedMessageId === message.id}
        on:copy={(event) => handleCopyMessage(event.detail.message)}
        on:openTool={(event) => handleOpenToolModal(event.detail.message)}
        on:openReasoning={(event) => handleOpenReasoningModal(event.detail.message)}
        on:openUsage={(event) => handleUsageClick(event.detail.id)}
      />
    </div>
  {/each}
</section>

<ToolUsageModal
  open={toolModalOpen}
  messageId={toolModalMessageId}
  tools={toolModalEntries}
  on:close={handleCloseToolModal}
/>

<ReasoningModal
  open={reasoningModalOpen}
  messageId={reasoningModalMessageId}
  segments={reasoningModalSegments}
  status={reasoningModalStatus}
  on:close={handleCloseReasoningModal}
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
  .conversation-item {
    padding: 0 2rem;
    max-width: min(800px, 100%);
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }
</style>
