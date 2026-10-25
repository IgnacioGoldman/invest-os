import type { SavedFilter } from "./personalization";
import { expressionFromMetricRules } from "./metricFilterRules";

export type ScreeningFilter = Pick<SavedFilter, "id" | "name" | "icon" | "expression" | "sort_key" | "sort_direction"> & {
  isDefault?: boolean;
  description?: string;
};

export const DEFAULT_FILTERS: ScreeningFilter[] = ([
  { id: "test-1", name: "pullback", timeframes: ["support_1m", "support_3m", "support_6m"] },
  { id: "test-2", name: "support", timeframes: ["support_1y", "support_2y", "support_5y"] },
] as const).map(({ id, name, timeframes }) => ({
  id: `default:${id}`,
  name,
  icon: "target",
  isDefault: true,
  description: `Strong or Solid revenue growth, profitable operations, at or near support on any of ${timeframes.map(field => field.replace("support_", "").toUpperCase()).join(", ")}, and no red flags in a complete assessment`,
  sort_key: "symbol",
  sort_direction: "asc",
  expression: expressionFromMetricRules([
    { id: `${id}-revenue`, field: "revenue", values: ["Strong", "Solid"] },
    { id: `${id}-margin`, field: "operating_margin", values: ["Profitable"] },
    { id: `${id}-support`, field: timeframes[0], timeframes: [...timeframes], timeframeMatch: "any", values: ["At Support", "Near Support"] },
    { id: `${id}-red-flags`, field: "red_flag_count", comparison: "eq", values: ["0"] },
  ], { operator: "and", groups: [] }),
}));
