import type { NumberFieldConfig } from './fields';

const sliderNumberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 4,
});

export function numericInputValue(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '';
}

export function formatParameterNumber(value: number, field: NumberFieldConfig): string {
  if (field.type === 'integer') {
    return String(Math.round(value));
  }
  return sliderNumberFormatter.format(value);
}
