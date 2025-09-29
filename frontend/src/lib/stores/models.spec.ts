import { describe, expect, it } from 'vitest';

import { __filterInternals, __selectorInternals, type MultiSelectFilter } from './models';

import type { ModelRecord } from '../api/types';

const { cycleMultiSelect, matchesMultiSelect, applySelectionState } = __filterInternals;
const { ensureSelectableModels, findModelById } = __selectorInternals;

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

describe('ensureSelectableModels', () => {
  const allModels: ModelRecord[] = [
    { id: 'model-a', name: 'Model A' },
    { id: 'model-b', name: 'Model B' },
    { id: 'model-c', name: 'Model C' },
  ];

  it('returns the base list when no model is selected', () => {
    const base = allModels.slice(1);
    const result = ensureSelectableModels(base, allModels, null);
    expect(result).toBe(base);
  });

  it('prepends the selected model when it is not part of the base list', () => {
    const base = allModels.slice(1);
    const result = ensureSelectableModels(base, allModels, 'model-a');
    expect(result[0].id).toBe('model-a');
    expect(result.slice(1)).toEqual(base);
  });

  it('ignores unknown model ids', () => {
    const base = allModels.slice(0, 2);
    const result = ensureSelectableModels(base, allModels, 'does-not-exist');
    expect(result).toBe(base);
  });

  it('returns an empty list when the base list is empty', () => {
    const result = ensureSelectableModels([], allModels, 'model-a');
    expect(result).toEqual([]);
  });
});

describe('findModelById', () => {
  const inventory: ModelRecord[] = [
    { id: 'x' },
    { id: 'y' },
  ];

  it('finds the model matching the provided id', () => {
    const result = findModelById(inventory, 'y');
    expect(result).toBe(inventory[1]);
  });

  it('returns null when the id is missing or not found', () => {
    expect(findModelById(inventory, null)).toBeNull();
    expect(findModelById(inventory, 'z')).toBeNull();
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
