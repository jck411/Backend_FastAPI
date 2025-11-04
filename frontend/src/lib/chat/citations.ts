export interface MessageCitation {
  url: string;
  title?: string;
  content?: string;
  startIndex?: number;
  endIndex?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function readString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function readIndex(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const parsed = Number.parseInt(trimmed, 10);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

function coerceCitation(value: unknown): MessageCitation | null {
  if (!isRecord(value)) {
    return null;
  }

  const url = readString(value.url);
  if (!url) {
    return null;
  }

  const citation: MessageCitation = { url };

  const title =
    readString(value.title) ??
    readString((value as Record<string, unknown>).name) ??
    readString((value as Record<string, unknown>).label);
  if (title) {
    citation.title = title;
  }

  const content =
    readString(value.content) ??
    readString((value as Record<string, unknown>).snippet) ??
    readString((value as Record<string, unknown>).text) ??
    readString((value as Record<string, unknown>).description);
  if (content) {
    citation.content = content;
  }

  const startIndex = readIndex(value.startIndex ?? (value as Record<string, unknown>).start_index);
  if (startIndex !== undefined) {
    citation.startIndex = startIndex;
  }

  const endIndex = readIndex(value.endIndex ?? (value as Record<string, unknown>).end_index);
  if (endIndex !== undefined) {
    citation.endIndex = endIndex;
  }

  return citation;
}

function coerceAnnotation(value: Record<string, unknown>): MessageCitation | null {
  const typeValue = readString(value.type);
  const normalizedType = typeValue ? typeValue.toLowerCase() : null;

  const payloadCandidates: unknown[] = [];
  if ('url_citation' in value) {
    payloadCandidates.push(value.url_citation);
  }
  if ('urlCitation' in value) {
    payloadCandidates.push((value as Record<string, unknown>).urlCitation);
  }
  if ('citation' in value) {
    payloadCandidates.push(value.citation);
  }
  if ('payload' in value) {
    payloadCandidates.push(value.payload);
  }
  if ('data' in value) {
    payloadCandidates.push(value.data);
  }

  for (const candidate of payloadCandidates) {
    const citation = coerceCitation(candidate);
    if (citation) {
      return citation;
    }
  }

  if (normalizedType === 'url_citation' || normalizedType === 'url-citation') {
    return coerceCitation(value);
  }

  return null;
}

function addUniqueCitation(
  collection: MessageCitation[],
  seen: Set<string>,
  citation: MessageCitation,
): void {
  const key = `${citation.url}|${citation.startIndex ?? ''}|${citation.endIndex ?? ''}`;
  if (seen.has(key)) {
    return;
  }
  seen.add(key);
  collection.push(citation);
}

export function collectCitations(...sources: unknown[]): MessageCitation[] {
  const results: MessageCitation[] = [];
  const seen = new Set<string>();
  const visited = new WeakSet<object>();
  const queue: unknown[] = [];

  function enqueue(value: unknown): void {
    if (value === undefined || value === null) {
      return;
    }
    if (Array.isArray(value) || isRecord(value)) {
      const objectValue = value as object;
      if (visited.has(objectValue)) {
        return;
      }
      visited.add(objectValue);
    }
    queue.push(value);
  }

  sources.forEach(enqueue);

  while (queue.length > 0) {
    const current = queue.shift();
    if (current === undefined || current === null) {
      continue;
    }

    if (Array.isArray(current)) {
      for (const item of current) {
        if (item === undefined || item === null) {
          continue;
        }
        if (Array.isArray(item) || isRecord(item)) {
          enqueue(item);
          continue;
        }
        const normalized = coerceCitation(item);
        if (normalized) {
          addUniqueCitation(results, seen, normalized);
        }
      }
      continue;
    }

    if (!isRecord(current)) {
      const normalized = coerceCitation(current);
      if (normalized) {
        addUniqueCitation(results, seen, normalized);
      }
      continue;
    }

    const annotationCitation = coerceAnnotation(current);
    if (annotationCitation) {
      addUniqueCitation(results, seen, annotationCitation);
    } else {
      const normalized = coerceCitation(current);
      if (normalized) {
        addUniqueCitation(results, seen, normalized);
      }
    }

    const nestedCandidates = [
      current.meta,
      current.metadata,
      current.annotations,
      current.citations,
      (current as Record<string, unknown>).url_citation,
      (current as Record<string, unknown>).urlCitation,
      current.payload,
      current.data,
      current.message,
    ];

    for (const candidate of nestedCandidates) {
      if (candidate === undefined || candidate === null) {
        continue;
      }
      if (Array.isArray(candidate) || isRecord(candidate)) {
        enqueue(candidate);
      } else {
        const normalized = coerceCitation(candidate);
        if (normalized) {
          addUniqueCitation(results, seen, normalized);
        }
      }
    }
  }

  return results;
}
