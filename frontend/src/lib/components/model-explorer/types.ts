import type { MultiSelectKey } from "../../stores/models";

export type FilterCategoryKey = MultiSelectKey;

export type FilterChipState = "include" | "exclude";

export interface FilterChip {
  id: string;
  category: FilterCategoryKey;
  categoryLabel: string;
  value: string;
  valueLabel: string;
  state: FilterChipState;
}
