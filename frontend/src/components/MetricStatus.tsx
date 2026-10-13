import type { MetricSignal } from "../metricStatus";
import "../metricStatus.css";

export function MetricStatus({ signal, context, className = "" }: {
  signal: MetricSignal;
  context?: string | null;
  className?: string;
}) {
  const label = context ? `${context} · ${signal.label}` : signal.label;
  const description = signal.detail ? `${label} · ${signal.detail}` : label;
  return (
    <span className={`metric-status metric-status-color metric-tone-${signal.tone} ${className}`.trim()} title={description} aria-label={description}>
      <span className="metric-status-dot" aria-hidden="true" />
      <span className="metric-status-label">{label}</span>
    </span>
  );
}
