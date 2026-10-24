import type { SavedFilter } from "./personalization";
import { expressionFromMetricRules } from "./metricFilterRules";

export type ScreeningFilter = Pick<SavedFilter, "id" | "name" | "icon" | "expression" | "sort_key" | "sort_direction"> & {
  isDefault?: boolean;
  description?: string;
};

export const DEFAULT_FILTERS: ScreeningFilter[] = [{
  id: "default:test-1",
  name: "test 1",
  icon: "target",
  isDefault: true,
  description: "Growing revenue, profitable operations, inside or near support on any of 1m, 3m or 6m",
  sort_key: "symbol",
  sort_direction: "asc",
  expression: expressionFromMetricRules([
    { id: "test-1-revenue", field: "revenue", values: ["Growing"] },
    { id: "test-1-margin", field: "operating_margin", values: ["Profitable"] },
    { id: "test-1-support", field: "support_1m", timeframes: ["support_1m", "support_3m", "support_6m"], timeframeMatch: "any", values: ["Inside Support Zone", "Near Support"] },
  ], { operator: "and", groups: [] }),
}];
