import { writable } from "svelte/store";
import type { ConversationMessage } from "../chat";
import type { ReasoningSegment, ReasoningStatus } from "../../chat/reasoning";

export type ReasoningModalState = {
  open: boolean;
  messageId: string | null;
  segments: ReasoningSegment[];
  status: ReasoningStatus | null;
};

const initialState: ReasoningModalState = {
  open: false,
  messageId: null,
  segments: [],
  status: null,
};

function segmentsEqual(a: ReasoningSegment[], b: ReasoningSegment[]): boolean {
  if (a.length !== b.length) {
    return false;
  }

  for (let index = 0; index < a.length; index += 1) {
    const first = a[index];
    const second = b[index];
    if (first.text !== second.text || first.type !== second.type) {
      return false;
    }
  }

  return true;
}

export function createReasoningModalStore() {
  const { subscribe, set, update } = writable<ReasoningModalState>(initialState);

  function openWithDetails(
    messageId: string,
    segments: ReasoningSegment[] | undefined,
    status: ReasoningStatus | null | undefined,
  ): void {
    set({
      open: true,
      messageId,
      segments: segments ?? [],
      status: status ?? null,
    });
  }

  function openForMessage(message: ConversationMessage): void {
    openWithDetails(message.id, message.details?.reasoning, message.details?.reasoningStatus);
  }

  function close(): void {
    set(initialState);
  }

  function syncFromMessages(messages: ConversationMessage[]): void {
    update((current) => {
      if (!current.open || !current.messageId) {
        return current;
      }

      const nextMessage = messages.find((message) => message.id === current.messageId);
      if (!nextMessage) {
        return initialState;
      }

      const nextSegments = nextMessage.details?.reasoning ?? [];
      const nextStatus = nextMessage.details?.reasoningStatus ?? null;

      if (segmentsEqual(nextSegments, current.segments) && nextStatus === current.status) {
        return current;
      }

      return {
        ...current,
        segments: nextSegments,
        status: nextStatus,
      };
    });
  }

  return {
    subscribe,
    openWithDetails,
    openForMessage,
    close,
    syncFromMessages,
  };
}
