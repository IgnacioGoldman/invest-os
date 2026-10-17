import type { FilterCondition, FilterExpression, FilterKey } from "./components/MobileStockExplorer";

export type MetricFilterRule = {
  id: string;
  field: FilterKey;
  values: string[];
};

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
  for (const clause of clauses) {
    if (clause.length === 0) continue;
    const field = clause[0].field;
    if (clause.some((condition) => condition.field !== field)) return { rules, logicChanged: true };
    const allowed = new Set(clause.map((condition) => condition.value));
    const previous = constraints.get(field);
    constraints.set(field, previous ? new Set([...previous].filter((value) => allowed.has(value))) : allowed);
  }
  const logicChanged = rules.some((rule) => {
    const allowed = constraints.get(rule.field);
    return !allowed || allowed.size !== rule.values.length || rule.values.some((value) => !allowed.has(value));
  });
  return { rules, logicChanged };
}

export function expressionFromMetricRules(rules: MetricFilterRule[], original: FilterExpression): FilterExpression {
  return {
    ...original,
    operator: "and",
    groups: rules.map((rule) => ({
      id: rule.id,
      operator: "or",
      conditions: rule.values.map((value, index) => ({ id: `${rule.id}-${index}`, field: rule.field, value })),
    })),
  };
}
