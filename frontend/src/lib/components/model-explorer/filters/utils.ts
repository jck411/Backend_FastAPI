import type { ModelSort, MultiSelectFilter } from "../../../stores/models";

export type FilterState = {
  search: string;
  inputModalities: MultiSelectFilter;
  outputModalities: MultiSelectFilter;
  series: MultiSelectFilter;
  providers: MultiSelectFilter;
  supportedParameters: MultiSelectFilter;
  moderation: MultiSelectFilter;
  minContext: number | null;
  minPromptPrice: number | null;
  maxPromptPrice: number | null;
  sort: ModelSort;
};

export const STOP_EPSILON = 1e-9;

export const CONTEXT_STOPS = [
  4000,
  16000,
  32000,
  64000,
  128000,
  256000,
  1_000_000,
];
export const CONTEXT_STOP_COUNT = CONTEXT_STOPS.length;
export const CONTEXT_ANY_INDEX = 0;

export function formatContextStop(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "Any";
  }
  if (value >= 1_000_000) {
    return "1M";
  }
  if (value >= 1000) {
    const rounded = Math.round(value / 1000);
    return `${rounded}K`;
  }
  return `${value}`;
}

export const CONTEXT_SCALE_LABELS = [
  "Any",
  ...CONTEXT_STOPS.map((value) => formatContextStop(value)),
];

export const PRICE_STOPS = [0, 0.1, 0.2, 0.5, 1, 5, 10];
export const PRICE_STOP_COUNT = PRICE_STOPS.length;
export const PRICE_UNBOUNDED_INDEX = PRICE_STOP_COUNT;
export const PRICE_UNBOUNDED_LABEL = "$10+";

export function formatStopLabel(value: number): string {
  if (value <= 0) {
    return "FREE";
  }
  const abs = Math.abs(value);
  const digits =
    abs >= 10 ? 0 : abs >= 1 ? 0 : abs >= 0.1 ? 1 : abs >= 0.01 ? 2 : 3;
  const formatted = value
    .toFixed(digits)
    .replace(/\.0+$/, "")
    .replace(/(\.\d*?)0+$/, "$1");
  return `$${formatted}`;
}

export const PRICE_SCALE_LABELS = PRICE_STOPS.map((stop) => formatStopLabel(stop));

export function clampIndex(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  if (value < min) return min;
  if (value > max) return max;
  return Math.round(value);
}

function findNearestStopIndex(value: number): number {
  let nearestIndex = 0;
  let nearestDiff = Number.POSITIVE_INFINITY;
  for (let index = 0; index < PRICE_STOP_COUNT; index += 1) {
    const diff = Math.abs(PRICE_STOPS[index] - value);
    if (diff < nearestDiff) {
      nearestDiff = diff;
      nearestIndex = index;
    }
  }
  return nearestIndex;
}

function findNearestContextIndex(value: number): number {
  let nearestIndex = 0;
  let nearestDiff = Number.POSITIVE_INFINITY;
  for (let index = 0; index < CONTEXT_STOP_COUNT; index += 1) {
    const diff = Math.abs(CONTEXT_STOPS[index] - value);
    if (diff < nearestDiff) {
      nearestDiff = diff;
      nearestIndex = index;
    }
  }
  return nearestIndex + 1;
}

export function indexForMinPrice(value: number | null): number {
  if (value === null || value <= 0) {
    return 0;
  }
  const exactIndex = PRICE_STOPS.findIndex((stop) => Math.abs(stop - value) <= STOP_EPSILON);
  if (exactIndex >= 0) {
    return exactIndex;
  }
  return findNearestStopIndex(value);
}

export function indexForMaxPrice(value: number | null): number {
  if (value === null) {
    return PRICE_UNBOUNDED_INDEX;
  }
  const exactIndex = PRICE_STOPS.findIndex((stop) => Math.abs(stop - value) <= STOP_EPSILON);
  if (exactIndex >= 0) {
    return exactIndex;
  }
  return findNearestStopIndex(value);
}

export function indexForContext(value: number | null): number {
  if (value === null || value <= 0) {
    return CONTEXT_ANY_INDEX;
  }
  for (let index = 0; index < CONTEXT_STOP_COUNT; index += 1) {
    if (Math.abs(CONTEXT_STOPS[index] - value) <= STOP_EPSILON) {
      return index + 1;
    }
  }
  return findNearestContextIndex(value);
}

export function valueForContextIndex(index: number): number | null {
  if (index <= CONTEXT_ANY_INDEX) {
    return null;
  }
  const stopIndex = Math.min(Math.max(index - 1, 0), CONTEXT_STOP_COUNT - 1);
  return CONTEXT_STOPS[stopIndex];
}

export function valueForMinIndex(index: number): number | null {
  if (index <= 0) {
    return null;
  }
  const safeIndex = Math.min(index, PRICE_STOP_COUNT - 1);
  return PRICE_STOPS[safeIndex];
}

export function valueForMaxIndex(index: number): number | null {
  if (index >= PRICE_UNBOUNDED_INDEX) {
    return null;
  }
  const safeIndex = Math.min(Math.max(index, 0), PRICE_STOP_COUNT - 1);
  return PRICE_STOPS[safeIndex];
}

export function countActiveFilters(filters: FilterState | undefined): number {
  if (!filters) return 0;
  let count = 0;
  if (filters.search.trim()) {
    count += 1;
  }

  const addSelectionCount = (selection: MultiSelectFilter) => {
    count += selection.include.length + selection.exclude.length;
  };

  addSelectionCount(filters.inputModalities);
  addSelectionCount(filters.outputModalities);
  addSelectionCount(filters.series);
  addSelectionCount(filters.providers);
  addSelectionCount(filters.supportedParameters);
  addSelectionCount(filters.moderation);

  if (filters.minContext !== null) {
    count += 1;
  }

  if (filters.minPromptPrice !== null) {
    count += 1;
  }

  if (filters.maxPromptPrice !== null) {
    count += 1;
  }

  return count;
}
