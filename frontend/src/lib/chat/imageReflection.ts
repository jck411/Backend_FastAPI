import type { AttachmentResource, ChatContentFragment } from '../api/types';

export const RECENT_ASSISTANT_IMAGE_LIMIT = 5;

export interface AssistantImageRecord {
  sessionId: string | null;
  messageId: string;
  url: string;
  createdAt: string;
  finalized: boolean;
}

export interface ImageReflectionIntent {
  shouldAttach: boolean;
  cleanedText: string;
  requestedCount: number | null;
  explicit: boolean;
  plural: boolean;
  attachAll: boolean;
}

const WORD_NUMBER: Record<string, number> = {
  zero: 0,
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
  couple: 2,
  pair: 2,
  both: 2,
};

function normaliseWhitespace(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function clampRequestedCount(value: number | null, available: number): number {
  if (value === null) {
    return 0;
  }
  const candidate = Number.isFinite(value) ? Math.max(1, value) : 1;
  return Math.min(candidate, available);
}

export function detectImageReflectionIntent(text: string): ImageReflectionIntent {
  if (!text) {
    return {
      shouldAttach: false,
      cleanedText: '',
      requestedCount: null,
      explicit: false,
      plural: false,
      attachAll: false,
    };
  }

  let cleanedText = text;
  let requestedCount: number | null = null;
  let attachAll = false;
  let explicit = false;

  cleanedText = cleanedText.replace(/@lastall/gi, () => {
    explicit = true;
    attachAll = true;
    return '';
  });

  cleanedText = cleanedText.replace(/@last(\d+)?/gi, (_match, digits: string | undefined) => {
    explicit = true;
    if (digits) {
      const parsed = Number.parseInt(digits, 10);
      if (Number.isFinite(parsed)) {
        requestedCount = Math.max(requestedCount ?? 0, parsed);
      }
    } else {
      requestedCount = Math.max(requestedCount ?? 0, 1);
    }
    return '';
  });

  cleanedText = normaliseWhitespace(cleanedText);

  const lower = cleanedText.toLowerCase();
  const pronounPattern = /\b(it|its|that|this|one)\b/;
  const imageTermPattern = /\b(image|picture|photo|render|artwork|drawing|result|shot)\b/;
  const lastOnePattern = /\b(last|previous)\s+(one|image|picture|photo|result)\b/;
  const pluralPronounPattern = /\b(them|those|these|they)\b/;
  const pluralImagePattern = /\b(images|pictures|photos|renders|drawings|results)\b/;
  const comparisonPattern = /\b(compare|comparison|difference|diff|versus|vs|side by side)\b/;
  const allPattern = /\b(all|every)\s+(of\s+)?(the\s+)?(image|images|pictures|photos|results)\b/;

  let plural = false;

  const lastCountMatch = lower.match(
    /\b(last|previous|past)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b/,
  );
  if (lastCountMatch) {
    const token = lastCountMatch[2];
    const wordCount = WORD_NUMBER[token] ?? Number.parseInt(token, 10);
    if (Number.isFinite(wordCount)) {
      requestedCount = Math.max(requestedCount ?? 0, wordCount);
    }
  }

  const explicitCountMatch = lower.match(
    /\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(images|pictures|photos|renders|results)\b/,
  );
  if (explicitCountMatch) {
    const token = explicitCountMatch[1];
    const wordCount = WORD_NUMBER[token] ?? Number.parseInt(token, 10);
    if (Number.isFinite(wordCount)) {
      requestedCount = Math.max(requestedCount ?? 0, wordCount);
    }
  }

  if (/\b(both|couple|pair)\b/.test(lower)) {
    requestedCount = Math.max(requestedCount ?? 0, 2);
  }

  if (allPattern.test(lower)) {
    attachAll = true;
  }

  const pluralSignals =
    pluralPronounPattern.test(lower) ||
    pluralImagePattern.test(lower) ||
    comparisonPattern.test(lower) ||
    (requestedCount !== null && requestedCount >= 2) ||
    attachAll;

  plural = pluralSignals;

  const shouldAttach =
    explicit ||
    imageTermPattern.test(lower) ||
    lastOnePattern.test(lower) ||
    pluralPronounPattern.test(lower) ||
    pluralImagePattern.test(lower) ||
    comparisonPattern.test(lower) ||
    pronounPattern.test(lower);

  return {
    shouldAttach,
    cleanedText,
    requestedCount,
    explicit,
    plural,
    attachAll,
  };
}

export function extractImageUrlsFromFragments(fragments: ChatContentFragment[]): string[] {
  if (!Array.isArray(fragments)) {
    return [];
  }
  const urls: string[] = [];
  for (const fragment of fragments) {
    if (!fragment || typeof fragment !== 'object') {
      continue;
    }
    if (fragment.type === 'image_url') {
      const image = (fragment as { image_url?: { url?: unknown } }).image_url;
      const url = image && typeof image.url === 'string' ? image.url : null;
      if (url && !urls.includes(url)) {
        urls.push(url);
      }
    }
  }
  return urls;
}

export function extractImageUrlsFromContent(content: unknown): string[] {
  if (!content) {
    return [];
  }
  if (typeof content === 'string') {
    return [];
  }
  return extractImageUrlsFromFragments(content as ChatContentFragment[]);
}

export function createImageRecords(
  urls: string[],
  sessionId: string | null,
  messageId: string,
  timestamp: string,
): AssistantImageRecord[] {
  const unique: string[] = [];
  for (const url of urls) {
    if (typeof url !== 'string' || !url || unique.includes(url)) {
      continue;
    }
    unique.push(url);
  }
  return unique.map((url) => ({
    sessionId,
    messageId,
    url,
    createdAt: timestamp,
    finalized: false,
  }));
}

export function mergeRecentAssistantImages(
  existing: AssistantImageRecord[],
  additions: AssistantImageRecord[],
  limit = RECENT_ASSISTANT_IMAGE_LIMIT,
): AssistantImageRecord[] {
  if (additions.length === 0) {
    return existing;
  }
  const additionUrls = new Set(additions.map((item) => item.url));
  const filtered = existing.filter((item) => !additionUrls.has(item.url));
  const merged = [...filtered, ...additions];
  if (merged.length > limit) {
    return merged.slice(merged.length - limit);
  }
  return merged;
}

export function markAssistantImagesFinalized(
  records: AssistantImageRecord[],
  messageId: string,
  sessionId: string | null,
): AssistantImageRecord[] {
  let mutated = false;
  const result = records.map((record) => {
    if (record.messageId !== messageId) {
      return record;
    }
    if (sessionId && record.sessionId && record.sessionId !== sessionId) {
      return record;
    }
    if (record.finalized) {
      return record;
    }
    mutated = true;
    return { ...record, sessionId: sessionId ?? record.sessionId, finalized: true };
  });
  return mutated ? result : records;
}

export function removeAssistantImagesForMessage(
  records: AssistantImageRecord[],
  messageId: string,
): AssistantImageRecord[] {
  if (!records.some((record) => record.messageId === messageId)) {
    return records;
  }
  return records.filter((record) => record.messageId !== messageId);
}

export function assignSessionToPendingRecords(
  records: AssistantImageRecord[],
  sessionId: string,
): AssistantImageRecord[] {
  if (!sessionId) {
    return records;
  }
  let mutated = false;
  const filtered: AssistantImageRecord[] = [];
  for (const record of records) {
    if (record.sessionId && record.sessionId !== sessionId) {
      mutated = true;
      continue;
    }
    if (record.sessionId === sessionId) {
      filtered.push(record);
      continue;
    }
    filtered.push({ ...record, sessionId });
    mutated = true;
  }
  return mutated ? filtered : records;
}

function resolveDesiredCount(
  intent: ImageReflectionIntent,
  available: number,
  limit: number,
): number {
  if (!intent.shouldAttach || available === 0) {
    return 0;
  }
  if (intent.attachAll) {
    return Math.min(available, limit);
  }
  if (intent.requestedCount !== null) {
    return clampRequestedCount(intent.requestedCount, available);
  }
  if (intent.plural) {
    const defaultCount = Math.min(2, available);
    return Math.min(defaultCount, limit);
  }
  return Math.min(1, available);
}

export function selectImagesForReflection(
  records: AssistantImageRecord[],
  sessionId: string | null,
  intent: ImageReflectionIntent,
  limit = RECENT_ASSISTANT_IMAGE_LIMIT,
): string[] {
  if (!intent.shouldAttach) {
    return [];
  }
  const scoped = records.filter((record) => {
    if (!sessionId) {
      return !record.sessionId;
    }
    return record.sessionId === sessionId || !record.sessionId;
  });

  if (scoped.length === 0) {
    return [];
  }

  const deduped: AssistantImageRecord[] = [];
  const seen = new Set<string>();
  for (const record of scoped) {
    if (!record.url || seen.has(record.url)) {
      continue;
    }
    seen.add(record.url);
    deduped.push(record);
  }

  const resolvedCount = resolveDesiredCount(intent, deduped.length, limit);
  if (resolvedCount <= 0) {
    return [];
  }

  const sorted = deduped.slice().sort((a, b) => {
    if (!a.createdAt && !b.createdAt) {
      return 0;
    }
    if (!a.createdAt) {
      return -1;
    }
    if (!b.createdAt) {
      return 1;
    }
    return a.createdAt.localeCompare(b.createdAt);
  });

  const selection = sorted.slice(-resolvedCount);
  return selection.map((record) => record.url);
}

export function createReflectedAttachmentResources(
  urls: string[],
  sessionId: string | null,
  idFactory: (prefix: string) => string,
): AttachmentResource[] {
  if (urls.length === 0) {
    return [];
  }
  const seen = new Set<string>();
  const now = new Date().toISOString();
  const unique: string[] = [];
  for (const url of urls) {
    if (typeof url !== 'string' || !url) {
      continue;
    }
    if (seen.has(url)) {
      continue;
    }
    seen.add(url);
    unique.push(url);
  }
  return unique.map((url) => ({
    id: idFactory('reflected'),
    sessionId: sessionId ?? '',
    mimeType: 'image/png',
    sizeBytes: 0,
    displayUrl: url,
    deliveryUrl: url,
    uploadedAt: now,
    expiresAt: null,
    metadata: { source: 'assistant_reflection' },
  }));
}
