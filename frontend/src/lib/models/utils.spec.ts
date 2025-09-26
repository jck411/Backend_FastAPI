import { describe, expect, it } from 'vitest';

import type { ModelRecord } from '../api/types';
import { extractModeration } from './utils';

describe('extractModeration', () => {
    it('returns "moderated" when provider indicates moderation', () => {
        const model = {
            id: 'moderated-model',
            top_provider: {
                is_moderated: true,
            },
        } as ModelRecord;

        expect(extractModeration(model)).toBe('moderated');
    });

    it('returns "unmoderated" when provider disables moderation', () => {
        const model = {
            id: 'unmoderated-model',
            top_provider: {
                is_moderated: false,
            },
        } as ModelRecord;

        expect(extractModeration(model)).toBe('unmoderated');
    });

    it('respects top-level boolean overrides', () => {
        const model = {
            id: 'override-model',
            top_provider: {
                is_moderated: true,
            },
            requires_moderation: false,
        } as ModelRecord;

        expect(extractModeration(model)).toBe('unmoderated');
    });

    it('returns null when no moderation boolean is present', () => {
        const model = {
            id: 'no-signal',
        } as ModelRecord;

        expect(extractModeration(model)).toBeNull();
    });
});
