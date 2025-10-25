import { describe, expect, it } from 'vitest';

import {
  assignSessionToPendingRecords,
  createImageRecords,
  createReflectedAttachmentResources,
  detectImageReflectionIntent,
  mergeRecentAssistantImages,
  selectImagesForReflection,
  type AssistantImageRecord,
} from './imageReflection';

describe('detectImageReflectionIntent', () => {
  it('detects simple pronoun references', () => {
    const intent = detectImageReflectionIntent('What color is it?');
    expect(intent.shouldAttach).toBe(true);
    expect(intent.plural).toBe(false);
    expect(intent.cleanedText).toBe('What color is it?');
  });

  it('detects plural requests with implicit count', () => {
    const intent = detectImageReflectionIntent('Compare the last two images for me.');
    expect(intent.shouldAttach).toBe(true);
    expect(intent.plural).toBe(true);
    expect(intent.requestedCount).toBeGreaterThanOrEqual(2);
  });

  it('supports explicit tokens and strips them', () => {
    const intent = detectImageReflectionIntent('@last2 Do they match?');
    expect(intent.shouldAttach).toBe(true);
    expect(intent.requestedCount).toBe(2);
    expect(intent.cleanedText).toBe('Do they match?');
  });
});

describe('selectImagesForReflection', () => {
  const makeRecord = (
    url: string,
    createdAt: string,
    finalized: boolean,
  ): AssistantImageRecord => ({
    sessionId: 'session-1',
    messageId: `msg-${url.slice(-1)}`,
    url,
    createdAt,
    finalized,
  });

  it('returns the most recent images when available', () => {
    const records: AssistantImageRecord[] = [
      makeRecord('https://example.test/a.png', '2024-01-01T00:00:00Z', true),
      makeRecord('https://example.test/b.png', '2024-01-01T00:01:00Z', false),
      makeRecord('https://example.test/c.png', '2024-01-01T00:02:00Z', true),
    ];
    const intent = detectImageReflectionIntent('Compare them side by side.');
    const urls = selectImagesForReflection(records, 'session-1', intent);
    expect(urls).toEqual([
      'https://example.test/b.png',
      'https://example.test/c.png',
    ]);
  });

  it('falls back to pending images when nothing is finalized', () => {
    const records: AssistantImageRecord[] = [
      makeRecord('https://example.test/a.png', '2024-01-01T00:00:00Z', false),
      makeRecord('https://example.test/b.png', '2024-01-01T00:01:00Z', false),
    ];
    const intent = detectImageReflectionIntent('What does it look like?');
    const urls = selectImagesForReflection(records, 'session-1', intent);
    expect(urls).toEqual(['https://example.test/b.png']);
  });
});

describe('recent assistant image bookkeeping', () => {
  it('merges new images and enforces the MRU limit', () => {
    const baseRecords = createImageRecords(
      [
        'https://example.test/a.png',
        'https://example.test/b.png',
        'https://example.test/c.png',
      ],
      'session-1',
      'assistant-1',
      '2024-01-01T00:00:00Z',
    ).map((record) => ({ ...record, finalized: true }));

    const additions = createImageRecords(
      [
        'https://example.test/d.png',
        'https://example.test/e.png',
      ],
      'session-1',
      'assistant-2',
      '2024-01-01T00:05:00Z',
    );

    const merged = mergeRecentAssistantImages(baseRecords, additions, 4);
    expect(merged).toHaveLength(4);
    expect(merged.map((record) => record.url)).toEqual([
      'https://example.test/b.png',
      'https://example.test/c.png',
      'https://example.test/d.png',
      'https://example.test/e.png',
    ]);
  });

  it('assigns pending records to a new session id', () => {
    const records: AssistantImageRecord[] = [
      {
        sessionId: null,
        messageId: 'assistant-1',
        url: 'https://example.test/a.png',
        createdAt: '2024-01-01T00:00:00Z',
        finalized: false,
      },
    ];

    const assigned = assignSessionToPendingRecords(records, 'session-123');
    expect(assigned[0]?.sessionId).toBe('session-123');
  });
});

describe('createReflectedAttachmentResources', () => {
  it('deduplicates urls and stamps metadata', () => {
    const attachments = createReflectedAttachmentResources(
      ['https://example.test/a.png', 'https://example.test/a.png'],
      'session-1',
      (prefix) => `${prefix}-id`,
    );
    expect(attachments).toHaveLength(1);
    expect(attachments[0]?.metadata).toMatchObject({ source: 'assistant_reflection' });
  });
});
