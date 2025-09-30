<script lang="ts">
  import { afterUpdate, createEventDispatcher, onDestroy } from "svelte";
  import type { ConversationMessage, ConversationRole } from "../../stores/chat";
  import ToolUsageModal from "./ToolUsageModal.svelte";
  import ReasoningModal from "./ReasoningModal.svelte";
  import MessageItem from "./MessageItem.svelte";
  import { computeMessagePresentation } from "./toolUsage.helpers";
  import { createToolUsageModalStore } from "../../stores/chatModals/toolUsageModal";
  import { createReasoningModalStore } from "../../stores/chatModals/reasoningModal";

  export let messages: ConversationMessage[] = [];
  export let disableDelete = false;

  let container: HTMLElement | null = null;
  let copiedMessageId: string | null = null;
  let copyResetTimeout: ReturnType<typeof setTimeout> | null = null;
  let visibleMessages: ConversationMessage[] = [];
  let assistantToolUsage: Record<string, boolean> = {};
  let messageIndexMap: Record<string, number> = {};
  const TOOL_ROLE: ConversationRole = "tool";
  let suppressNextScroll = false;
  const SCROLL_LOCK_THRESHOLD = 12;
  let autoScroll = true;

  const toolUsageModal = createToolUsageModalStore();
  const reasoningModal = createReasoningModalStore();

  const dispatch = createEventDispatcher<{
    openGenerationDetails: { id: string };
    deleteMessage: { id: string };
    retryMessage: { id: string };
    editMessage: { id: string };
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
    toolUsageModal.openForMessage(messages, messageIndexMap, message.id, TOOL_ROLE);
  }

  function handleCloseToolModal(): void {
    toolUsageModal.close();
  }

  function handleOpenReasoningModal(message: ConversationMessage): void {
    reasoningModal.openForMessage(message);
  }

  function handleCloseReasoningModal(): void {
    reasoningModal.close();
  }

  function handleDeleteMessage(message: ConversationMessage): void {
    if (!message) {
      return;
    }
    dispatch('deleteMessage', { id: message.id });
  }

  function handleRetryMessage(message: ConversationMessage): void {
    if (!message) {
      return;
    }
    dispatch('retryMessage', { id: message.id });
  }

  function handleEditMessage(message: ConversationMessage): void {
    if (!message) {
      return;
    }
    dispatch('editMessage', { id: message.id });
  }

  $: toolUsageModal.syncEntries(messages, messageIndexMap, TOOL_ROLE);
  $: reasoningModal.syncFromMessages(messages);
</script>

<section class="conversation" bind:this={container} aria-live="polite" on:scroll={handleScroll}>
  {#each visibleMessages as message (message.id)}
    <div class="conversation-item">
      <MessageItem
        {message}
        showToolIndicator={assistantToolUsage[message.id]}
        copied={copiedMessageId === message.id}
        disableDelete={disableDelete}
        on:copy={(event) => handleCopyMessage(event.detail.message)}
        on:openTool={(event) => handleOpenToolModal(event.detail.message)}
        on:openReasoning={(event) => handleOpenReasoningModal(event.detail.message)}
        on:openUsage={(event) => handleUsageClick(event.detail.id)}
        on:delete={(event) => handleDeleteMessage(event.detail.message)}
        on:retry={(event) => handleRetryMessage(event.detail.message)}
        on:edit={(event) => handleEditMessage(event.detail.message)}
      />
    </div>
  {/each}
</section>

<ToolUsageModal
  open={$toolUsageModal.open}
  messageId={$toolUsageModal.messageId}
  tools={$toolUsageModal.tools}
  on:close={handleCloseToolModal}
/>

<ReasoningModal
  open={$reasoningModal.open}
  messageId={$reasoningModal.messageId}
  segments={$reasoningModal.segments}
  status={$reasoningModal.status}
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
