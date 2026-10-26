export type MetricTone = "strong" | "positive" | "warning" | "negative" | "neutral";
export type MetricSignal = { label: string; tone: MetricTone; detail?: string };

// Support colors describe proximity; business colors describe direction, never investment quality.
export function metricSignal(label: string): MetricSignal {
  const tone: MetricTone = label === "At Support" ? "strong"
    : label === "Above Support" ? "warning"
    : label === "Near Support" || label === "Strong" || label === "Solid" || label === "Growing" || label === "Accelerating" || label === "Improving" || label === "Up today" ? "positive"
    : label === "Weak" || label === "Choppy" || label === "Decelerating" || label === "Declining" || label === "Loss-making" || label === "Down today" ? "negative" : "neutral";
  return { label, tone };
}
