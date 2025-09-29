export interface ReasoningSegment {
  text: string;
  type?: string;
}

export type ReasoningStatus = 'streaming' | 'complete';

export function toReasoningSegments(value: unknown): ReasoningSegment[] {
  if (value == null) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((entry) => toReasoningSegments(entry));
  }
  if (typeof value === 'string') {
    return value.length > 0 ? [{ text: value }] : [];
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const text = record.text;
    const type = record.type;
    const segments: ReasoningSegment[] = [];

    if (typeof text === 'string' && text.length > 0) {
      const segment: ReasoningSegment = { text };
      if (typeof type === 'string' && type.length > 0) {
        segment.type = type;
      }
      segments.push(segment);
    }

    const nestedKeys = [
      'segments',
      'segment',
      'messages',
      'message',
      'content',
      'contents',
      'parts',
      'steps',
      'items',
    ];

    for (const key of nestedKeys) {
      const nested = record[key];
      if (nested !== undefined) {
        segments.push(...toReasoningSegments(nested));
      }
    }

    return segments;
  }

  return [];
}

export function collectReasoningSegmentsFromChunk(chunk: unknown): {
  segments: ReasoningSegment[];
  hasPayload: boolean;
} {
  if (!chunk || typeof chunk !== 'object') {
    return { segments: [], hasPayload: false };
  }
  const choices = (chunk as { choices?: Array<Record<string, unknown>> }).choices;
  if (!Array.isArray(choices)) {
    return { segments: [], hasPayload: false };
  }
  const segments: ReasoningSegment[] = [];
  let hasPayload = false;
  for (const choice of choices) {
    if (!choice || typeof choice !== 'object') {
      continue;
    }
    const delta = (choice as { delta?: unknown }).delta;
    if (!delta || typeof delta !== 'object') {
      continue;
    }
    if ('reasoning' in (delta as Record<string, unknown>)) {
      hasPayload = true;
      const reasoning = (delta as { reasoning?: unknown }).reasoning;
      segments.push(...toReasoningSegments(reasoning));
    }
  }
  return { segments, hasPayload };
}

export function mergeReasoningSegments(
  existing: ReasoningSegment[] | undefined,
  incoming: ReasoningSegment[],
): ReasoningSegment[] {
  const sanitizedIncoming = incoming.filter((segment) => segment.text.length > 0);
  if (sanitizedIncoming.length === 0) {
    return existing ?? [];
  }
  if (!existing || existing.length === 0) {
    return sanitizedIncoming;
  }

  const existingText = existing.map((segment) => segment.text).join('');
  const incomingText = sanitizedIncoming.map((segment) => segment.text).join('');

  if (incomingText.startsWith(existingText)) {
    const suffix = incomingText.slice(existingText.length);
    if (suffix.length === 0) {
      return existing;
    }
    const merged = [...existing];
    const lastIndex = merged.length - 1;
    const lastIncoming = sanitizedIncoming[sanitizedIncoming.length - 1];
    merged[lastIndex] = {
      text: `${merged[lastIndex].text}${suffix}`,
      type: lastIncoming.type ?? merged[lastIndex].type,
    };
    return merged;
  }

  const merged = [...existing];
  for (const segment of sanitizedIncoming) {
    const alreadyPresent = merged.some(
      (existingSegment) =>
        existingSegment.text === segment.text && existingSegment.type === segment.type,
    );
    if (alreadyPresent) {
      continue;
    }
    merged.push(segment);
  }
  return merged;
}

export function reasoningTextLength(
  segments: ReasoningSegment[] | undefined | null,
): number {
  return segments?.reduce((total, segment) => total + segment.text.length, 0) ?? 0;
}
