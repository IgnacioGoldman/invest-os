import type { OpenDataMetric } from "./api";

export type MetricTone = "strong" | "positive" | "warning" | "negative" | "neutral";
export type MetricSignal = { label: string; tone: MetricTone; detail?: string };

// Green communicates a favorable direction only, never investment quality.
export function metricSignal(label: string): MetricSignal {
  const tone: MetricTone = label === "Accelerating" || label === "Up today" ? "positive"
    : label === "Decelerating" || label === "Declining" || label === "Down today" ? "negative" : "neutral";
  return { label, tone };
}

function signalValue(valueOrMetric?: number | OpenDataMetric | null) {
  const value = typeof valueOrMetric === "object" ? valueOrMetric?.value : valueOrMetric;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function supportSignal(value?: number | null): MetricSignal {
  const distance = signalValue(value);
  if (distance == null || distance < -2.5) return { label: "Unknown", tone: "neutral", detail: "No usable support zone was detected for this window." };
  return metricSignal(distance <= 2.5 ? "Inside Support Zone" : distance <= 6 ? "Near Support" : "Above Support");
}
