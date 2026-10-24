import type { FilterCondition, FilterExpression, FilterKey } from "./components/MobileStockExplorer";
import type { OpenDataStockSnapshot } from "./api";
import { hasDisabledFilter, isSupportField, normalizedFilterValue, stockMetricForField, supportMetric, SUPPORT_FILTER_KEYS, type SupportFilterKey } from "./stockMetrics";

export function filterExpressionMatches(snapshot: OpenDataStockSnapshot, expression: FilterExpression) {
  if (hasDisabledFilter(expression)) return false;
  if (expression.groups.length === 0) return true;
  const groupMatches = expression.groups.map((group) => {
    if (group.conditions.length === 0) return true;
    const matches = group.conditions.map((condition) => {
      const label = isSupportField(condition.field)
        ? supportMetric(snapshot, condition.field)?.signal.label ?? "Unknown"
        : stockMetricForField(condition.field)?.getSignal(snapshot).label ?? "Unclear";
      return label === normalizedFilterValue(condition.field, condition.value);
    });
    return group.operator === "and" ? matches.every(Boolean) : matches.some(Boolean);
  });
  return expression.operator === "and" ? groupMatches.every(Boolean) : groupMatches.some(Boolean);
}

export type MetricFilterRule = {
  id: string;
  field: FilterKey;
  values: string[];
  timeframes?: SupportFilterKey[];
  timeframeMatch?: "any" | "all";
};

export function metricRuleFields(rule: MetricFilterRule): FilterKey[] {
  return isSupportField(rule.field) ? rule.timeframes ?? [rule.field] : [rule.field];
}

// Present support rules with the same allowed values as one multi-select condition.
// Keep different value sets separate so editing existing filters preserves their meaning.
export function groupSupportTimeframes(rules: MetricFilterRule[]): MetricFilterRule[] {
  const grouped: MetricFilterRule[] = [];
  for (const rule of rules) {
    if (!isSupportField(rule.field)) {
      grouped.push(rule);
      continue;
    }
    const matching = rule.timeframeMatch !== "any" && grouped.find((other) => isSupportField(other.field)
      && other.timeframeMatch !== "any"
      && other.values.length === rule.values.length
      && other.values.every((value) => rule.values.includes(value)));
    if (matching) {
      const fields = [...metricRuleFields(matching), ...metricRuleFields(rule)];
      matching.timeframes = SUPPORT_FILTER_KEYS.filter((field) => fields.includes(field));
    } else {
      grouped.push({ ...rule, timeframes: [...(rule.timeframes ?? [rule.field])] });
    }
  }
  return grouped;
}

export function metricRulesFromExpression(expression: FilterExpression) {
  const valuesByField = new Map<FilterKey, Set<string>>();
  for (const condition of expression.groups.flatMap((group) => group.conditions)) {
    const values = valuesByField.get(condition.field) ?? new Set<string>();
    values.add(condition.value);
    valuesByField.set(condition.field, values);
  }
  const rules: MetricFilterRule[] = Array.from(valuesByField, ([field, values]) => ({
    id: `metric-${field}`, field, values: [...values],
  }));

  // Recognize older expressions that already mean "all metrics, any value".
  // Other saved filters remain untouched until the user saves the new rules.
  let clauses: FilterCondition[][];
  if (expression.operator === "and" || expression.groups.length <= 1) {
    clauses = expression.groups.flatMap((group) => group.operator === "and"
      ? group.conditions.map((condition) => [condition]) : [group.conditions]);
  } else if (valuesByField.size === 1 && expression.groups.every((group) => group.conditions.length > 0
    && (group.operator === "or" || new Set(group.conditions.map((condition) => condition.value)).size === 1))) {
    clauses = [expression.groups.flatMap((group) => group.conditions)];
  } else {
    return { rules, logicChanged: rules.length > 0 };
  }
  const constraints = new Map<FilterKey, Set<string>>();
  const alternatives = new Map<FilterKey, MetricFilterRule>();
  for (const clause of clauses) {
    if (clause.length === 0) continue;
    const field = clause[0].field;
    if (clause.some((condition) => condition.field !== field)) {
      const fields = [...new Set(clause.map((condition) => condition.field))];
      const timeframes = SUPPORT_FILTER_KEYS.filter((key) => fields.includes(key));
      const values = [...new Set(clause.filter((condition) => condition.field === field).map((condition) => condition.value))];
      // An OR across support timeframes is one rule only when each timeframe
      // accepts the same values and is not independently constrained elsewhere.
      if (timeframes.length !== fields.length || fields.some((key) => {
        const allowed = new Set(clause.filter((condition) => condition.field === key).map((condition) => condition.value));
        return allowed.size !== values.length || values.some((value) => !allowed.has(value))
          || clauses.some((other) => other !== clause && other.some((condition) => condition.field === key));
      })) return { rules, logicChanged: true };
      const rule: MetricFilterRule = { id: `metric-${field}`, field, values, timeframes, timeframeMatch: "any" };
      fields.forEach((key) => alternatives.set(key, rule));
      continue;
    }
    const allowed = new Set(clause.map((condition) => condition.value));
    const previous = constraints.get(field);
    constraints.set(field, previous ? new Set([...previous].filter((value) => allowed.has(value))) : allowed);
  }
  const parsedRules = rules.flatMap((rule) => {
    const alternative = alternatives.get(rule.field);
    return alternative ? alternative.field === rule.field ? [alternative] : [] : [rule];
  });
  const logicChanged = parsedRules.some((rule) => {
    if (rule.timeframeMatch === "any") return false;
    const allowed = constraints.get(rule.field);
    return !allowed || allowed.size !== rule.values.length || rule.values.some((value) => !allowed.has(value));
  });
  return { rules: parsedRules, logicChanged };
}

export function expressionFromMetricRules(rules: MetricFilterRule[], original: FilterExpression): FilterExpression {
  return {
    ...original,
    operator: "and",
    groups: rules.flatMap((rule) => {
      const fields = metricRuleFields(rule);
      if (isSupportField(rule.field) && rule.timeframeMatch === "any") return [{
        id: rule.id,
        operator: "or" as const,
        conditions: fields.flatMap((field) => rule.values.map((value, index) => ({ id: `${rule.id}-${field}-${index}`, field, value }))),
      }];
      return fields.map((field) => {
        const id = rule.timeframes ? `${rule.id}-${field}` : rule.id;
        return {
          id,
          operator: "or" as const,
          conditions: rule.values.map((value, index) => ({ id: `${id}-${index}`, field, value })),
        };
      });
    }),
  };
}
