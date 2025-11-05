<script lang="ts">
  import { afterUpdate, createEventDispatcher, onDestroy } from "svelte";
  import type { AttachmentResource } from "../../api/types";
  import { collectCitations } from "../../chat/citations";
  import type {
    ConversationMessage,
    ConversationRole,
  } from "../../stores/chat";
  import { createCitationsModalStore } from "../../stores/chatModals/citationsModal";
  import { createReasoningModalStore } from "../../stores/chatModals/reasoningModal";
  import { createToolUsageModalStore } from "../../stores/chatModals/toolUsageModal";
  import { createWebSearchDetailsModalStore } from "../../stores/chatModals/webSearchDetailsModal";
  import CitationsModal from "./CitationsModal.svelte";
  import MessageItem from "./MessageItem.svelte";
  import ReasoningModal from "./ReasoningModal.svelte";
  import { computeMessagePresentation } from "./toolUsage.helpers";
  import ToolUsageModal from "./ToolUsageModal.svelte";
  import WebSearchDetailsModal from "./WebSearchDetailsModal.svelte";

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
  const citationsModal = createCitationsModalStore();
  const webSearchDetailsModal = createWebSearchDetailsModalStore();

  const dispatch = createEventDispatcher<{
    openGenerationDetails: { id: string };
    deleteMessage: { id: string };
    retryMessage: { id: string };
    editMessage: { id: string };
    editAssistantAttachment: {
      message: ConversationMessage;
      attachment: AttachmentResource;
    };
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

  async function handleCopyMessage(
    message: ConversationMessage,
  ): Promise<void> {
    try {
      await navigator.clipboard.writeText(message.text ?? "");
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
    toolUsageModal.openForMessage(
      messages,
      messageIndexMap,
      message.id,
      TOOL_ROLE,
    );
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

  function handleOpenCitationsModal(message: ConversationMessage): void {
    const citations = collectCitations(
      message.details?.citations ?? null,
      message.details?.meta ?? null,
      message.details ?? null,
    );
    citationsModal.openWithCitations(message.id, citations);
  }

  function handleCloseCitationsModal(): void {
    citationsModal.close();
  }

  function handleOpenWebSearchDetailsModal(message: ConversationMessage): void {
    webSearchDetailsModal.openForMessage(message);
  }

  function handleCloseWebSearchDetailsModal(): void {
    webSearchDetailsModal.close();
  }

  function handleDeleteMessage(message: ConversationMessage): void {
    if (!message) {
      return;
    }
    dispatch("deleteMessage", { id: message.id });
  }

  function handleRetryMessage(message: ConversationMessage): void {
    if (!message) {
      return;
    }
    dispatch("retryMessage", { id: message.id });
  }

  function handleEditMessage(message: ConversationMessage): void {
    if (!message) {
      return;
    }
    dispatch("editMessage", { id: message.id });
  }

  function handleAssistantAttachmentEdit(detail: {
    message: ConversationMessage;
    attachment: AttachmentResource;
  }): void {
    if (!detail?.message || !detail?.attachment) {
      return;
    }
    dispatch("editAssistantAttachment", detail);
  }

  $: toolUsageModal.syncEntries(messages, messageIndexMap, TOOL_ROLE);
  $: reasoningModal.syncFromMessages(messages);
</script>

<section
  class="conversation"
  bind:this={container}
  aria-live="polite"
  on:scroll={handleScroll}
>
  {#each visibleMessages as message (message.id)}
    <div class="conversation-item">
      <MessageItem
        {message}
        showToolIndicator={assistantToolUsage[message.id]}
        copied={copiedMessageId === message.id}
        {disableDelete}
        on:copy={(event) => handleCopyMessage(event.detail.message)}
        on:openTool={(event) => handleOpenToolModal(event.detail.message)}
        on:openReasoning={(event) =>
          handleOpenReasoningModal(event.detail.message)}
        on:openCitations={(event) =>
          handleOpenCitationsModal(event.detail.message)}
        on:openWebSearchDetails={(event) =>
          handleOpenWebSearchDetailsModal(event.detail.message)}
        on:openUsage={(event) => handleUsageClick(event.detail.id)}
        on:delete={(event) => handleDeleteMessage(event.detail.message)}
        on:retry={(event) => handleRetryMessage(event.detail.message)}
        on:edit={(event) => handleEditMessage(event.detail.message)}
        on:editAttachment={(event) =>
          handleAssistantAttachmentEdit(event.detail)}
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

<CitationsModal
  open={$citationsModal.open}
  messageId={$citationsModal.messageId}
  citations={$citationsModal.citations}
  on:close={handleCloseCitationsModal}
/>

<WebSearchDetailsModal
  open={$webSearchDetailsModal.open}
  messageId={$webSearchDetailsModal.messageId}
  details={$webSearchDetailsModal.details}
  on:close={handleCloseWebSearchDetailsModal}
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
  @media (max-width: 900px) {
    .conversation {
      padding: 1.5rem 0;
      gap: 1.25rem;
    }
    .conversation-item {
      padding: 0 1.5rem;
    }
  }
  @media (max-width: 600px) {
    .conversation {
      padding: 1rem 0;
      gap: 1rem;
    }
    .conversation-item {
      padding: 0 1rem;
    }
  }
  @media (max-width: 420px) {
    .conversation-item {
      padding: 0 0.75rem;
    }
  }
</style>
