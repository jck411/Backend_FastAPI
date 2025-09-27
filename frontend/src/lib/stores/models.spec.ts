import { describe, expect, it } from 'vitest';

import { __filterInternals, type MultiSelectFilter } from './models';

const { cycleMultiSelect, matchesMultiSelect, applySelectionState } = __filterInternals;

function emptySelection(): MultiSelectFilter {
  return { include: [], exclude: [] };
}

describe('cycleMultiSelect', () => {
  it('cycles include → exclude → neutral for the same value', () => {
    const first = cycleMultiSelect(emptySelection(), 'Tools');
    expect(first).toEqual({ include: ['tools'], exclude: [] });

    const second = cycleMultiSelect(first, 'Tools');
    expect(second).toEqual({ include: [], exclude: ['tools'] });

    const third = cycleMultiSelect(second, 'Tools');
    expect(third).toEqual({ include: [], exclude: [] });
  });

  it('ignores empty or whitespace-only values', () => {
    const initial = emptySelection();
    const result = cycleMultiSelect(initial, '   ');
    expect(result).toBe(initial);
  });
});

describe('matchesMultiSelect', () => {
  it('requires all included values to be present', () => {
    const selection: MultiSelectFilter = {
      include: ['tools', 'vision'],
      exclude: [],
    };

    expect(matchesMultiSelect(selection, ['vision', 'tools', 'audio'])).toBe(true);
    expect(matchesMultiSelect(selection, ['tools'])).toBe(false);
  });

  it('rejects models containing excluded values', () => {
    const selection: MultiSelectFilter = {
      include: [],
      exclude: ['temperature'],
    };

    expect(matchesMultiSelect(selection, ['tools', 'reasoning'])).toBe(true);
    expect(matchesMultiSelect(selection, ['tools', 'temperature'])).toBe(false);
  });

  it('supports combined include and exclude filters', () => {
    const selection: MultiSelectFilter = {
      include: ['tools'],
      exclude: ['temperature'],
    };

    expect(matchesMultiSelect(selection, ['tools'])).toBe(true);
    expect(matchesMultiSelect(selection, ['tools', 'temperature'])).toBe(false);
    expect(matchesMultiSelect(selection, ['temperature'])).toBe(false);
  });
});

describe('applySelectionState', () => {
  it('sets the requested state without cycling through intermediate states', () => {
    const base: MultiSelectFilter = { include: ['tools'], exclude: ['temperature'] };

    const neutral = applySelectionState(base, 'tools', 'neutral');
    expect(neutral.include).not.toContain('tools');
    expect(neutral.exclude).toContain('temperature');

    const included = applySelectionState(neutral, 'temperature', 'include');
    expect(included.include).toContain('temperature');
    expect(included.exclude).not.toContain('temperature');
  });
});
