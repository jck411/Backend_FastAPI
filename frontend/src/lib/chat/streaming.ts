import { streamChat } from '../api/client';
import type { ChatCompletionChunk, ChatCompletionRequest } from '../api/types';
import { collectReasoningSegmentsFromChunk, type ReasoningSegment } from './reasoning';

export interface ChatStreamMessageDelta {
  text: string;
  reasoningSegments: ReasoningSegment[];
  hasReasoningPayload: boolean;
  chunk: ChatCompletionChunk;
}

interface ChatStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onMessageDelta?: (delta: ChatStreamMessageDelta) => void;
  onMetadata?: (payload: Record<string, unknown>) => void;
  onToolEvent?: (payload: Record<string, unknown>) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

export interface ChatStreamOptions extends ChatStreamCallbacks {
  signal?: AbortSignal;
}

export async function startChatStream(
  payload: ChatCompletionRequest,
  options: ChatStreamOptions = {},
): Promise<void> {
  const { signal, onSession, onMessageDelta, onMetadata, onToolEvent, onDone, onError } = options;

  await streamChat(payload, {
    signal,
    onSession,
    onDone,
    onError,
    onChunk(chunk, rawEvent) {
      const eventType = rawEvent?.event ?? 'message';

      if (eventType === 'message') {
        const deltaText = chunk.choices?.map((choice) => choice.delta?.content ?? '').join('') ?? '';
        const { segments: reasoningSegments, hasPayload: hasReasoningPayload } =
          collectReasoningSegmentsFromChunk(chunk);

        if (!deltaText && reasoningSegments.length === 0 && !hasReasoningPayload) {
          return;
        }

        onMessageDelta?.({
          text: deltaText,
          reasoningSegments,
          hasReasoningPayload,
          chunk,
        });
        return;
      }

      if (eventType === 'metadata' && rawEvent?.data) {
        try {
          const metadata = JSON.parse(rawEvent.data) as Record<string, unknown>;
          onMetadata?.(metadata);
        } catch (error) {
          console.warn('Failed to parse metadata payload', error, rawEvent.data);
        }
        return;
      }

      if (eventType === 'tool' && rawEvent?.data) {
        try {
          const payload = JSON.parse(rawEvent.data) as Record<string, unknown>;
          onToolEvent?.(payload);
        } catch (error) {
          console.warn('Failed to parse tool payload', error, rawEvent.data);
        }
      }
    },
  });
}
