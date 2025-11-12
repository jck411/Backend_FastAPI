<script lang="ts">
  import {
    BarChart,
    Brain,
    Check,
    ClipboardCopy,
    Globe,
    Pencil,
    RefreshCcw,
    Trash2,
    Wrench,
  } from "lucide-svelte";
  import { createEventDispatcher } from "svelte";
  import { copyableCode } from "../../actions/copyableCode";
  import type { AttachmentResource } from "../../api/types";
  import { collectCitations } from "../../chat/citations";
  import type { ConversationMessage, MessageCitation } from "../../stores/chat";
  import { renderMarkdown } from "../../utils/markdown";
  import type { AssistantToolUsageSummary } from "./toolUsage.helpers";

  export let message: ConversationMessage;
  export let toolSummary: AssistantToolUsageSummary | undefined;
  export let copied = false;
  export let disableDelete = false;

  const dispatch = createEventDispatcher<{
    copy: { message: ConversationMessage };
    openTool: { message: ConversationMessage };
    openReasoning: { message: ConversationMessage };
    openCitations: { message: ConversationMessage };
    openWebSearchDetails: { message: ConversationMessage };
    openUsage: { id: string };
    edit: { message: ConversationMessage };
    editAttachment: {
      message: ConversationMessage;
      attachment: AttachmentResource;
    };
    retry: { message: ConversationMessage };
    delete: { message: ConversationMessage };
  }>();

  let hasReasoningSegments = false;
  let citations: MessageCitation[] = [];
  let hasWebSearchConfig = false;
  let showToolIndicator = false;
  let toolIndicatorTitle = "View tool usage";
  let toolCountLabel: string | null = null;
  let toolTokensLabel: string | null = null;

  const toolTokenFormatter = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 0,
  });

  $:
    toolCountLabel =
      toolSummary?.count && toolSummary.count > 0 ? `×${toolSummary.count}` : null;
  $:
    toolTokensLabel =
      toolSummary?.tokens?.totalTokens != null
        ? `${toolTokenFormatter.format(toolSummary.tokens.totalTokens)} tokens`
        : null;
  $: showToolIndicator = Boolean(toolSummary?.used);
  $: toolIndicatorTitle = (() => {
    const details: string[] = [];
    if (toolSummary?.count && toolSummary.count > 0) {
      details.push(
        `${toolSummary.count} ${toolSummary.count === 1 ? "hop" : "hops"}`,
      );
    }
    if (toolTokensLabel) {
      details.push(`${toolTokensLabel}`);
    }
    if (details.length === 0) {
      return "View tool usage";
    }
    return `View tool usage — ${details.join(", ")}`;
  })();

  $: hasReasoningSegments =
    (message.details?.reasoning?.length ?? 0) > 0 ||
    Boolean(message.details?.reasoningStatus);

  $: {
    const webSearchResults = message.details?.meta?.web_search_results;

    // DEBUG: Log EVERYTHING about this message
    if (message.role === "assistant") {
      console.log("=== FULL MESSAGE DEBUG ===");
      console.log("Message ID:", message.id);
      console.log("Message role:", message.role);
      console.log("Message.details:", JSON.stringify(message.details, null, 2));
      console.log("webSearchResults:", webSearchResults);
      console.log("Is Array?", Array.isArray(webSearchResults));
      console.log(
        "Length:",
        Array.isArray(webSearchResults) ? webSearchResults.length : 0,
      );
      console.log("========================");
    }

    if (Array.isArray(webSearchResults) && webSearchResults.length > 0) {
      citations = webSearchResults
        .map((result: any) => ({
          url: result.url || "",
          title: result.title || result.name || "",
          content: result.snippet || result.content || result.description || "",
        }))
        .filter((c: any) => c.url);
      console.log("Citations extracted:", citations);
    } else {
      // Extract citations from metadata AND message content (markdown links)
      citations = collectCitations(
        message.details?.citations ?? null,
        message.details?.meta ?? null,
        message.details ?? null,
        message.content ?? null,
        {
          content: typeof message.content === "string" ? message.content : null,
        },
      );
      console.log("Citations from collectCitations:", citations);
    }
  }

  $: hasCitations = citations.length > 0;
  $: hasWebSearchConfig = Boolean(message.details?.webSearchConfig);

  function handleCopy(): void {
    dispatch("copy", { message });
  }

  function handleOpenReasoning(): void {
    dispatch("openReasoning", { message });
  }

  function handleOpenTool(): void {
    dispatch("openTool", { message });
  }

  function handleOpenCitations(): void {
    dispatch("openCitations", { message });
  }

  function handleOpenWebSearchDetails(): void {
    dispatch("openWebSearchDetails", { message });
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

  function handleAttachmentEdit(attachment: AttachmentResource): void {
    dispatch("editAttachment", { message, attachment });
  }

  function attachmentFilename(attachment: AttachmentResource): string | null {
    const value = attachment.metadata?.filename;
    return typeof value === "string" && value.trim() ? value : null;
  }

  function attachmentLabel(attachment: AttachmentResource): string {
    const filename = attachmentFilename(attachment);
    return filename ? `Open attachment ${filename}` : "Open attachment";
  }

  function attachmentAlt(attachment: AttachmentResource): string {
    const filename = attachmentFilename(attachment);
    return filename ?? "Attachment preview";
  }

  $: hasAttachments = (message.attachments?.length ?? 0) > 0;

  type TimestampInfo = {
    iso: string;
    display: string;
    tooltip: string;
  } | null;

  const EDT_TIMEZONE = "America/New_York";

  function formatUtcTooltip(value: string | null | undefined): string | null {
    if (!value) {
      return null;
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "UTC",
      weekday: "short",
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).formatToParts(date);
    const lookup = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((part) => part.type === type)?.value ?? "";
    const weekday = lookup("weekday");
    const month = lookup("month");
    const day = lookup("day");
    const year = lookup("year");
    const hour = lookup("hour");
    const minute = lookup("minute");
    const second = lookup("second");
    return `${weekday} ${month} ${day} ${year} ${hour}:${minute}:${second} UTC`.replace(
      /\s+/g,
      " ",
    );
  }

  function computeTimestampInfo(
    value: string | null | undefined,
    utcValue: string | null | undefined,
  ): TimestampInfo {
    if (!value) {
      return null;
    }
    const candidate =
      typeof value === "string" && value ? value : String(value);
    const date = new Date(candidate);
    if (Number.isNaN(date.getTime())) {
      return {
        iso: candidate,
        display: candidate,
        tooltip: candidate,
      };
    }
    try {
      const partsFormatter = new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
        timeZone: EDT_TIMEZONE,
        timeZoneName: "short",
      });
      const parts = partsFormatter.formatToParts(date);
      const lookup = (type: Intl.DateTimeFormatPartTypes) =>
        parts.find((part) => part.type === type)?.value ?? "";
      const hour = lookup("hour");
      const minute = lookup("minute");
      const second = lookup("second");
      const dayPeriod = lookup("dayPeriod");
      const tzName = lookup("timeZoneName");
      const display =
        `${hour}:${minute} ${dayPeriod}${tzName ? ` ${tzName}` : ""}`.trim();
      const tooltipTime =
        `${hour}:${minute}:${second} ${dayPeriod}${tzName ? ` ${tzName}` : ""}`.trim();
      const tooltipFormatter = new Intl.DateTimeFormat(undefined, {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: EDT_TIMEZONE,
        timeZoneName: "short",
      });
      const utcTooltip = formatUtcTooltip(utcValue ?? value);
      const tooltipBase = `${tooltipFormatter.format(date)} (${tooltipTime})`;
      const tooltip = utcTooltip
        ? `${tooltipBase}\n${utcTooltip}`
        : tooltipBase;
      return {
        iso: candidate,
        display,
        tooltip,
      };
    } catch (error) {
      console.warn("Failed to format timestamp", error);
      const utcTooltip = formatUtcTooltip(utcValue ?? value);
      return {
        iso: candidate,
        display: date.toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
        }),
        tooltip: utcTooltip ?? candidate,
      };
    }
  }

  $: timestampInfo = computeTimestampInfo(
    message.createdAt,
    message.createdAtUtc,
  );
</script>

<article class={`message ${message.role}`}>
  <div class="bubble" class:has-attachments={hasAttachments}>
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
                  class:streaming={message.details?.reasoningStatus ===
                    "streaming"}
                  aria-label="View reasoning trace"
                  title={message.details?.reasoningStatus === "streaming"
                    ? "Reasoning stream in progress"
                    : "View reasoning trace"}
                  on:click={handleOpenReasoning}
                >
                  <Brain size={14} strokeWidth={1.8} aria-hidden="true" />
                </button>
              {/if}
              {#if hasWebSearchConfig}
                <button
                  type="button"
                  class="sender-citation-indicator"
                  aria-label="View web search details"
                  title="View web search details"
                  on:click={handleOpenWebSearchDetails}
                >
                  <Globe size={14} strokeWidth={1.8} aria-hidden="true" />
                </button>
              {/if}
              {#if showToolIndicator}
                <button
                  type="button"
                  class="sender-tool-indicator"
                  aria-label={toolIndicatorTitle}
                  title={toolIndicatorTitle}
                  on:click={handleOpenTool}
                >
                  <Wrench size={14} strokeWidth={1.8} aria-hidden="true" />
                  {#if toolCountLabel}
                    <span class="sender-tool-count">{toolCountLabel}</span>
                  {/if}
                  {#if toolTokensLabel}
                    <span class="sender-tool-tokens">{toolTokensLabel}</span>
                  {/if}
                </button>
              {/if}
            </span>
          {/if}
        </span>
      </span>
    {/if}
    <div class="message-content" use:copyableCode>
      {#if message.text}
        {@html renderMarkdown(message.text)}
      {/if}
      {#if message.attachments?.length}
        <div class="message-attachments">
          {#each message.attachments as attachment (attachment.id ?? attachment.displayUrl ?? attachment.deliveryUrl)}
            <figure class="attachment-card">
              <div class="attachment-shell">
                <a
                  class="attachment-link"
                  href={attachment.displayUrl || attachment.deliveryUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={attachmentLabel(attachment)}
                >
                  <img
                    src={attachment.displayUrl || attachment.deliveryUrl}
                    alt={attachmentAlt(attachment)}
                    loading="lazy"
                  />
                </a>
                {#if message.role === "assistant"}
                  <button
                    type="button"
                    class="attachment-edit"
                    aria-label="Edit and resend image"
                    title="Edit and resend image"
                    on:click={() => handleAttachmentEdit(attachment)}
                  >
                    <Pencil size={14} strokeWidth={1.8} aria-hidden="true" />
                    <span class="attachment-edit-label">Edit &amp; send</span>
                  </button>
                {/if}
              </div>
            </figure>
          {/each}
        </div>
      {/if}
    </div>
    {#if timestampInfo}
      <div class="message-meta">
        <time datetime={timestampInfo.iso} title={timestampInfo.tooltip}>
          {timestampInfo.display}
        </time>
      </div>
    {/if}
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
        <button
          type="button"
          class="message-action"
          aria-label="Edit message"
          on:click={handleEdit}
        >
          <Pencil size={16} strokeWidth={1.6} aria-hidden="true" />
        </button>
        <button
          type="button"
          class="message-action"
          aria-label="Retry message"
          on:click={handleRetry}
        >
          <RefreshCcw size={16} strokeWidth={1.6} aria-hidden="true" />
        </button>
      {/if}
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
  .message-meta {
    margin-top: 0.35rem;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.65);
    display: flex;
  }
  .message.assistant .message-meta {
    justify-content: flex-start;
  }
  .message.user .message-meta {
    justify-content: flex-end;
  }
  .message-meta time {
    letter-spacing: 0.02em;
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
    gap: 0.35rem;
    min-height: 1.5rem;
    padding: 0.2rem 0.5rem;
    border-radius: 999px;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.1);
    border: 1px solid rgba(56, 189, 248, 0.25);
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
  }
  .sender-tool-indicator:hover,
  .sender-tool-indicator:focus-visible {
    color: #7dd3fc;
    background: rgba(56, 189, 248, 0.18);
    border-color: rgba(125, 211, 252, 0.55);
    outline: none;
  }
  .sender-tool-count {
    font-size: 0.7rem;
    font-weight: 700;
  }
  .sender-tool-tokens {
    font-size: 0.7rem;
    font-weight: 500;
    color: rgba(148, 233, 255, 0.9);
  }
  .sender-citation-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1rem;
    height: 1rem;
    color: #facc15;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
  }
  .sender-citation-indicator:hover,
  .sender-citation-indicator:focus-visible {
    color: #fde68a;
    outline: none;
  }
  .message-content {
    line-height: 1.55;
    font-size: 0.95rem;
    color: #e2e8f8;
    overflow: visible;
  }
  .message-content :global(p) {
    margin: 0 0 0.85rem;
  }
  .message-content :global(p:last-child) {
    margin-bottom: 0;
  }
  .message-content :global(code) {
    font-family: "Fira Code", "SFMono-Regular", Menlo, Monaco, Consolas,
      "Liberation Mono", "Courier New", monospace;
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
  .message-content :global(img) {
    display: block;
    max-width: 100%;
    height: auto;
    margin: 0.85rem 0;
  }
  .bubble.has-attachments {
    max-width: 100%;
  }
  .message-attachments {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 0.85rem;
    width: 100%;
  }
  .message-attachments .attachment-card {
    margin: 0;
    width: 100%;
  }
  .message-attachments .attachment-card .attachment-shell {
    position: relative;
  }
  .message-attachments .attachment-card .attachment-link {
    display: block;
    width: 100%;
    border-radius: 0.75rem;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(16, 24, 40, 0.45);
    transition:
      transform 0.12s ease,
      border-color 0.12s ease;
  }
  .message.user .message-attachments .attachment-card .attachment-link {
    background: rgba(42, 59, 96, 0.6);
  }
  .message-attachments .attachment-card .attachment-link:hover,
  .message-attachments .attachment-card .attachment-link:focus-visible {
    border-color: rgba(147, 197, 253, 0.65);
    transform: translateY(-1px);
    outline: none;
  }
  .message-attachments .attachment-card img {
    display: block;
    width: 100%;
    height: auto;
    max-height: 70vh;
    object-fit: contain;
  }
  .message-attachments .attachment-edit {
    position: absolute;
    left: 50%;
    bottom: 0.85rem;
    transform: translate(-50%, 8px);
    opacity: 0;
    pointer-events: none;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    border-radius: 999px;
    border: 1px solid rgba(147, 197, 253, 0.75);
    background: rgba(8, 14, 28, 0.82);
    color: #e2e8f0;
    font-size: 0.75rem;
    letter-spacing: 0.01em;
    text-transform: uppercase;
    transition:
      opacity 0.15s ease,
      transform 0.15s ease;
    z-index: 2;
  }
  .message-attachments .attachment-shell:hover .attachment-edit,
  .message-attachments .attachment-edit:focus-visible {
    opacity: 1;
    transform: translate(-50%, 0);
    pointer-events: auto;
    outline: none;
  }
  .message-attachments .attachment-edit:hover {
    background: rgba(30, 42, 72, 0.92);
    border-color: rgba(180, 207, 255, 0.85);
  }
  .message-attachments .attachment-edit :global(svg) {
    width: 0.85rem;
    height: 0.85rem;
  }
  .message-attachments .attachment-edit-label {
    font-weight: 600;
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
  .message:focus-within .message-actions,
  .message-actions:hover {
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
