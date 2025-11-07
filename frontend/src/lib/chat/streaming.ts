import { streamChat } from '../api/client';
import type {
  ChatCompletionChunk,
  ChatCompletionRequest,
  ChatContentFragment,
} from '../api/types';
import { collectReasoningSegmentsFromChunk, type ReasoningSegment } from './reasoning';

export interface ChatStreamMessageDelta {
  text: string;
  fragments: ChatContentFragment[];
  reasoningSegments: ReasoningSegment[];
  hasReasoningPayload: boolean;
  chunk: ChatCompletionChunk;
}

interface ChatStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onMessageDelta?: (delta: ChatStreamMessageDelta) => void;
  onMetadata?: (payload: Record<string, unknown>) => void;
  onToolEvent?: (payload: Record<string, unknown>) => void;
  onNotice?: (payload: Record<string, unknown>) => void;
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
  const { onNotice } = options;

  await streamChat(payload, {
    signal,
    onSession,
    onDone,
    onError,
    onNotice,
    onChunk(chunk, rawEvent) {
      const eventType = rawEvent?.event ?? 'message';

      if (eventType === 'message') {
        const { text: deltaText, fragments: deltaFragments } = extractDeltaContentAndFragments(
          chunk,
        );
        const { segments: reasoningSegments, hasPayload: hasReasoningPayload } =
          collectReasoningSegmentsFromChunk(chunk);

        if (
          !deltaText &&
          deltaFragments.length === 0 &&
          reasoningSegments.length === 0 &&
          !hasReasoningPayload
        ) {
          return;
        }

        onMessageDelta?.({
          text: deltaText,
          fragments: deltaFragments,
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

function extractDeltaContentAndFragments(
  chunk: ChatCompletionChunk,
): { text: string; fragments: ChatContentFragment[] } {
  const textParts: string[] = [];
  const fragments: ChatContentFragment[] = [];

  const choices = chunk.choices ?? [];
  for (const choice of choices) {
    const delta = choice.delta ?? {};
    const content = delta.content;
    if (typeof content === 'string') {
      if (content) {
        textParts.push(content);
      }
    } else if (Array.isArray(content)) {
      for (const fragment of content) {
        if (fragment && typeof fragment === 'object') {
          fragments.push(fragment as ChatContentFragment);
        }
      }
    }

    const images = delta.images;
    if (Array.isArray(images)) {
      for (const image of images) {
        if (image && typeof image === 'object') {
          fragments.push(image as ChatContentFragment);
        }
      }
    }
  }

  return {
    text: textParts.join(''),
    fragments,
  };
}
