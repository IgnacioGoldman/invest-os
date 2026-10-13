import type { OpenDataMetric } from "./api";

export type MetricTone = "strong" | "positive" | "warning" | "negative" | "neutral";
export type MetricSignal = { label: string; tone: MetricTone; detail?: string };

// Every metric uses the same five levels: best, good, moderate, caution, unknown.
export function metricSignal(label: string): MetricSignal {
  let tone: MetricTone;
  switch (label) {
    case "At support":
    case "Strong":
    case "Cheap":
    case "Accelerating":
    case "This week":
      tone = "strong";
      break;
    case "Near support":
    case "Solid":
    case "Fair":
    case "Next 30 days":
    case "Up today":
      tone = "positive";
      break;
    case "Above support":
    case "Flat":
    case "Modest":
    case "Thin":
    case "Stable":
    case "Pricey":
    case "Later":
    case "Flat today":
      tone = "warning";
      break;
    case "Far":
    case "Weak":
    case "Very pricey":
    case "Decelerating":
    case "Down today":
      tone = "negative";
      break;
    default:
      tone = "neutral";
  }
  return { label, tone };
}

function signalValue(valueOrMetric?: number | OpenDataMetric | null) {
  const value = typeof valueOrMetric === "object" ? valueOrMetric?.value : valueOrMetric;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function growthSignal(valueOrMetric?: number | OpenDataMetric | null, modestLabel = "Modest"): MetricSignal {
  const value = signalValue(valueOrMetric);
  if (value == null) {
    return metricSignal(typeof valueOrMetric === "object" && valueOrMetric?.tier === "unavailable_open_free"
      ? "Unavailable" : "Unclear");
  }
  return metricSignal(value >= 20 ? "Strong" : value >= 8 ? "Solid" : value >= 0 ? modestLabel : "Weak");
}

export function revenueGrowthSignal(valueOrMetric?: number | OpenDataMetric | null): MetricSignal {
  return growthSignal(valueOrMetric, "Flat");
}

export function fcfMarginSignal(value?: number | null): MetricSignal {
  const margin = signalValue(value);
  if (margin == null) return metricSignal("Unclear");
  return metricSignal(margin >= 20 ? "Strong" : margin >= 10 ? "Solid" : margin >= 0 ? "Thin" : "Weak");
}

export function supportSignal(value?: number | null): MetricSignal {
  const distance = signalValue(value);
  if (distance == null) {
    return { label: "Far", tone: "neutral", detail: "No usable support zone was detected for this window." };
  }
  return metricSignal(distance <= 2.5 ? "At support" : distance <= 6 ? "Near support" : distance <= 25 ? "Above support" : "Far");
}

export function forwardPeSignal(valueOrMetric?: number | OpenDataMetric | null): MetricSignal {
  const value = signalValue(valueOrMetric);
  if (value == null || value <= 0) return metricSignal("Unclear");
  return metricSignal(value <= 18 ? "Cheap" : value <= 25 ? "Fair" : value >= 50 ? "Very pricey" : value >= 35 ? "Pricey" : "Unclear");
}
