import type {
  AttachmentResource,
  ChatContentFragment,
  ChatMessageContent,
} from '../api/types';

export type MessageContentPart =
  | { type: 'text'; text: string }
  | {
    type: 'image';
    attachmentId?: string;
    url: string;
    displayUrl: string;
    mimeType?: string;
    sizeBytes?: number;
    fileName?: string;
    sessionId?: string;
    expiresAt?: string | null;
    uploadedAt?: string;
    metadata?: Record<string, unknown> | null;
  };

export interface NormalizedMessageContent {
  parts: MessageContentPart[];
  text: string;
}

interface ImageMetadata {
  attachment_id?: unknown;
  display_url?: unknown;
  mime_type?: unknown;
  size_bytes?: unknown;
  filename?: unknown;
  session_id?: unknown;
  uploaded_at?: unknown;
  expires_at?: unknown;
  [key: string]: unknown;
}

export function buildChatContent(
  text: string,
  attachments: AttachmentResource[],
): ChatMessageContent {
  const trimmed = text.trim();
  const fragments: ChatContentFragment[] = [];

  if (trimmed) {
    fragments.push({ type: 'text', text: trimmed });
  }

  for (const attachment of attachments) {
    fragments.push({
      type: 'image_url',
      image_url: {
        url: attachment.deliveryUrl,
      },
      metadata: {
        attachment_id: attachment.id,
        display_url: attachment.displayUrl,
        mime_type: attachment.mimeType,
        size_bytes: attachment.sizeBytes,
        filename: attachment.metadata?.filename,
        session_id: attachment.sessionId,
        uploaded_at: attachment.uploadedAt,
        expires_at: attachment.expiresAt,
      },
    });
  }

  if (fragments.length === 1 && fragments[0].type === 'text') {
    return fragments[0].text as ChatMessageContent;
  }

  return (fragments.length > 0 ? fragments : '') as ChatMessageContent;
}

export function normalizeMessageContent(content: ChatMessageContent): NormalizedMessageContent {
  if (typeof content === 'string') {
    const text = content;
    return {
      parts: text ? [{ type: 'text', text }] : [],
      text,
    };
  }

  const parts: MessageContentPart[] = [];
  const textParts: string[] = [];

  for (const fragment of content) {
    if (fragment?.type === 'text' && typeof fragment.text === 'string') {
      const value = fragment.text;
      parts.push({ type: 'text', text: value });
      textParts.push(value);
      continue;
    }
    if (fragment?.type === 'image_url' && 'image_url' in fragment) {
      const image = fragment.image_url as { url: string;[key: string]: unknown };
      if (!image || typeof image.url !== 'string') {
        continue;
      }
      const metadata = (fragment.metadata ?? {}) as ImageMetadata;
      const displayUrl =
        typeof metadata.display_url === 'string' && metadata.display_url
          ? metadata.display_url
          : image.url;
      const attachmentId =
        typeof metadata.attachment_id === 'string' && metadata.attachment_id
          ? metadata.attachment_id
          : undefined;
      const mimeType =
        typeof metadata.mime_type === 'string' && metadata.mime_type
          ? metadata.mime_type
          : undefined;
      const sizeBytes =
        typeof metadata.size_bytes === 'number' && Number.isFinite(metadata.size_bytes)
          ? Number(metadata.size_bytes)
          : undefined;
      const fileName =
        typeof metadata.filename === 'string' && metadata.filename
          ? metadata.filename
          : undefined;
      const sessionId =
        typeof metadata.session_id === 'string' && metadata.session_id
          ? metadata.session_id
          : undefined;
      const uploadedAt =
        typeof metadata.uploaded_at === 'string' && metadata.uploaded_at
          ? metadata.uploaded_at
          : undefined;
      const expiresAt =
        typeof metadata.expires_at === 'string' && metadata.expires_at
          ? metadata.expires_at
          : null;

      parts.push({
        type: 'image',
        url: image.url,
        displayUrl,
        attachmentId,
        mimeType,
        sizeBytes,
        fileName,
        sessionId,
        uploadedAt,
        expiresAt,
        metadata: (fragment.metadata ?? null) as Record<string, unknown> | null,
      });
    }
  }

  const text = textParts.join('\n').trim();
  return { parts, text };
}
