import { writable } from "svelte/store";
import type { ConversationMessage, ConversationRole } from "../chat";
import type { ToolUsageEntry } from "../../components/chat/toolUsage.types";
import { deriveToolUsageEntries } from "../../components/chat/toolUsage.helpers";

export type ToolUsageModalState = {
  open: boolean;
  messageId: string | null;
  tools: ToolUsageEntry[];
};

const initialState: ToolUsageModalState = {
  open: false,
  messageId: null,
  tools: [],
};

export function createToolUsageModalStore() {
  const { subscribe, set, update } = writable<ToolUsageModalState>(initialState);

  function openWithEntries(messageId: string, tools: ToolUsageEntry[]): void {
    set({
      open: true,
      messageId,
      tools,
    });
  }

  function openForMessage(
    messages: ConversationMessage[],
    messageIndexMap: Record<string, number>,
    messageId: string,
    toolRole: ConversationRole,
  ): void {
    const tools = deriveToolUsageEntries(messages, messageIndexMap, messageId, toolRole);
    openWithEntries(messageId, tools);
  }

  function close(): void {
    set(initialState);
  }

  function syncEntries(
    messages: ConversationMessage[],
    messageIndexMap: Record<string, number>,
    toolRole: ConversationRole,
  ): void {
    update((current) => {
      if (!current.open || !current.messageId) {
        return current;
      }

      const tools = deriveToolUsageEntries(
        messages,
        messageIndexMap,
        current.messageId,
        toolRole,
      );

      const unchanged =
        tools.length === current.tools.length &&
        tools.every((tool, index) => {
          const previous = current.tools[index];
          return (
            previous?.id === tool.id &&
            previous?.name === tool.name &&
            previous?.status === tool.status &&
            previous?.input === tool.input &&
            previous?.result === tool.result
          );
        });

      if (unchanged) {
        return current;
      }

      return {
        ...current,
        tools,
      };
    });
  }

  return {
    subscribe,
    openWithEntries,
    openForMessage,
    close,
    syncEntries,
  };
}
