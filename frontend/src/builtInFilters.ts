import type { FilterExpression } from "./components/MobileStockExplorer";
import { expressionFromMetricRules, metricRulesFromExpression, type MetricFilterRule } from "./metricFilterRules";

export const PULLBACK_SUPPORT_FILTER_KEYS = ["support_1m", "support_3m", "support_6m"] as const;
export const SUPPORT_PRESET_FILTER_KEYS = ["support_1y", "support_2y", "support_5y"] as const;
export type BuiltInPreset = "pullback" | "support" | "earnings";

function metricRule(field: MetricFilterRule["field"], values: string[]): MetricFilterRule {
  return { id: `builtin-${field}`, field, values };
}

export function createBuiltInPresetExpression(preset: BuiltInPreset): FilterExpression {
  const growth = metricRule("revenue", ["Strong", "Solid"]);
  const rules = preset === "earnings"
    ? [metricRule("upcoming_earnings", ["This week", "Next 30 days"]), growth]
    : [
      ...(preset === "pullback" ? PULLBACK_SUPPORT_FILTER_KEYS : SUPPORT_PRESET_FILTER_KEYS)
        .map((field) => metricRule(field, ["At support", "Near support"])),
      growth,
      metricRule("forward_pe", ["Cheap", "Fair"]),
    ];
  return expressionFromMetricRules(rules, { operator: "and", groups: [] });
}

function ruleSignature(rules: MetricFilterRule[]) {
  return JSON.stringify(rules.map(({ field, values }) => [field, [...values].sort()])
    .sort(([left], [right]) => String(left).localeCompare(String(right))));
}

export function builtInPresetFor(expression: FilterExpression): BuiltInPreset | null {
  const { rules, logicChanged } = metricRulesFromExpression(expression);
  if (logicChanged) return null;
  return (["support", "pullback", "earnings"] as const).find((preset) =>
    ruleSignature(rules) === ruleSignature(metricRulesFromExpression(createBuiltInPresetExpression(preset)).rules),
  ) ?? null;
}

export const BUILT_IN_PRESET_COPY: Record<BuiltInPreset, { name: string; summary: string }> = {
  support: {
    name: "Strong growth + support",
    summary: "Companies with Strong or Solid latest revenue growth YoY and Cheap or Fair Forward P/E (positive and up to 25×), with price at or near support in each of the 1Y, 2Y, and 5Y timeframes.",
  },
  pullback: {
    name: "Strong YoY + pullback + fair price",
    summary: "Companies with Strong or Solid latest revenue growth YoY and Cheap or Fair Forward P/E (positive and up to 25×), with price at or near support in each of the 1M, 3M, and 6M timeframes.",
  },
  earnings: {
    name: "Growth + upcoming earnings",
    summary: "Companies reporting earnings this week or in the next 30 days with Strong or Solid latest revenue growth YoY.",
  },
};
