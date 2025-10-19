import { streamChat } from '../api/client';
import type {
  ChatCompletionChunk,
  ChatCompletionRequest,
  ChatMessageContent,
  ChatContentFragment,
} from '../api/types';
import { normalizeMessageContent, type NormalizedMessageContent } from './content';
import { collectReasoningSegmentsFromChunk, type ReasoningSegment } from './reasoning';

export interface ChatStreamMessageDelta {
  text: string;
  content?: ChatMessageContent | null;
  normalizedContent?: NormalizedMessageContent | null;
  reasoningSegments: ReasoningSegment[];
  hasReasoningPayload: boolean;
  chunk: ChatCompletionChunk;
}

export interface ChatStreamMetadataPayload {
  metadata: Record<string, unknown>;
  content?: ChatMessageContent | null;
  normalizedContent?: NormalizedMessageContent | null;
}

interface ChatStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onMessageDelta?: (delta: ChatStreamMessageDelta) => void;
  onMetadata?: (payload: ChatStreamMetadataPayload) => void;
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
        const textPieces: string[] = [];
        const fragmentAccumulator: ChatContentFragment[] = [];

        for (const choice of chunk.choices ?? []) {
          const deltaContent = choice.delta?.content;
          if (typeof deltaContent === 'string') {
            if (deltaContent) {
              textPieces.push(deltaContent);
              fragmentAccumulator.push({ type: 'text', text: deltaContent });
            }
            continue;
          }

          if (Array.isArray(deltaContent)) {
            for (const item of deltaContent) {
              if (item && typeof item === 'object') {
                fragmentAccumulator.push(item as ChatContentFragment);
              }
            }
          }
        }

        let messageContent: ChatMessageContent | null = null;
        if (fragmentAccumulator.length > 0) {
          messageContent = fragmentAccumulator;
        } else if (textPieces.length > 0) {
          messageContent = textPieces.join('');
        }

        const normalizedContent =
          messageContent !== null ? normalizeMessageContent(messageContent) : null;
        const deltaText = normalizedContent?.text ?? textPieces.join('');
        const { segments: reasoningSegments, hasPayload: hasReasoningPayload } =
          collectReasoningSegmentsFromChunk(chunk);

        if (
          !deltaText &&
          fragmentAccumulator.length === 0 &&
          reasoningSegments.length === 0 &&
          !hasReasoningPayload
        ) {
          return;
        }

        onMessageDelta?.({
          text: deltaText,
          content: messageContent,
          normalizedContent,
          reasoningSegments,
          hasReasoningPayload,
          chunk,
        });
        return;
      }

      if (eventType === 'metadata' && rawEvent?.data) {
        try {
          const metadata = JSON.parse(rawEvent.data) as Record<string, unknown>;
          const content = resolveMessageContentFromMetadata(metadata);
          const normalizedContent =
            content !== null ? normalizeMessageContent(content) : null;
          onMetadata?.({
            metadata,
            content,
            normalizedContent,
          });
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

function resolveMessageContentFromMetadata(
  metadata: Record<string, unknown>,
): ChatMessageContent | null {
  const messageCandidate = metadata['message'];
  if (messageCandidate && typeof messageCandidate === 'object') {
    const innerContent = (messageCandidate as Record<string, unknown>)['content'];
    const resolved = coerceChatMessageContent(innerContent);
    if (resolved !== null) {
      return resolved;
    }
  }

  if ('content' in metadata) {
    const resolved = coerceChatMessageContent(metadata['content']);
    if (resolved !== null) {
      return resolved;
    }
  }

  return null;
}

function coerceChatMessageContent(value: unknown): ChatMessageContent | null {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value as ChatContentFragment[];
  }

  return null;
}
