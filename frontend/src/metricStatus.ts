export type MetricTone = "strong" | "positive" | "warning" | "negative" | "neutral";
export type MetricSignal = { label: string; tone: MetricTone; detail?: string };

// Green communicates a favorable direction only, never investment quality.
export function metricSignal(label: string): MetricSignal {
  const tone: MetricTone = label === "Growing" || label === "Accelerating" || label === "Improving" || label === "Up today" ? "positive"
    : label === "Decelerating" || label === "Declining" || label === "Loss-making" || label === "Down today" ? "negative" : "neutral";
  return { label, tone };
}
