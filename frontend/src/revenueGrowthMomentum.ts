type RevenueRow = {
  period: string;
  as_of?: string;
  metrics: Record<string, { value?: number | null }>;
};
type RevenueSnapshot = { historical_series: Record<string, RevenueRow[]> };
export type RevenueGrowthPoint = { period: string; value: number };
export type RevenueGrowthMomentum = {
  label: "Accelerating" | "Decelerating" | "Stable" | "Unclear";
  change: number | null;
  recentMedian: number | null;
  priorMedian: number | null;
  latestChange: number | null;
  latestMovement: "Rebounding" | "Improving" | "Weakening" | "Steady" | null;
  points: RevenueGrowthPoint[];
  reason: string | null;
};

export const REVENUE_MOMENTUM_DESCRIPTION =
  "Compares the median revenue YoY growth of the latest three quarters with the median of the preceding three quarters. The median is the middle growth rate in each group, so one unusual quarter has less influence. Changes of at least 3 percentage points indicate acceleration or deceleration. The latest quarter's movement is shown separately to distinguish a rebound from a sustained change in growth pace.";

function quarterIndex(period: string): number | null {
  const match = /^FY(\d+)\s+Q([1-4])$/.exec(period);
  return match ? Number(match[1]) * 4 + Number(match[2]) - 1 : null;
}

function median(points: RevenueGrowthPoint[]) {
  return points.map((point) => point.value).sort((a, b) => a - b)[1];
}

export function calculateRevenueGrowthMomentum(snapshot: RevenueSnapshot): RevenueGrowthMomentum {
  const unclear = (reason: string): RevenueGrowthMomentum => ({
    label: "Unclear", change: null, recentMedian: null, priorMedian: null,
    latestChange: null, latestMovement: null, points: [], reason,
  });
  const rows = [...(snapshot.historical_series.quarterly_revenue ?? [])];
  if (rows.some((row) => quarterIndex(row.period) == null)) {
    return unclear("Quarterly revenue history contains an invalid fiscal period.");
  }
  const sortKey = (row: RevenueRow) => row.as_of || String(quarterIndex(row.period)).padStart(8, "0");
  rows.sort((a, b) => sortKey(a).localeCompare(sortKey(b)));
  const window = rows.slice(-6);
  if (window.length < 6) return unclear("Needs six consecutive quarters with comparable revenue YoY growth.");
  if (window.some((row, index) => index > 0 && quarterIndex(row.period)! !== quarterIndex(window[index - 1].period)! + 1)) {
    return unclear("The latest six revenue quarters contain a gap or duplicate fiscal period.");
  }
  const points: RevenueGrowthPoint[] = [];
  for (const row of window) {
    const value = row.metrics.revenue_growth_yoy?.value;
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return unclear(`${row.period} has no comparable revenue YoY growth.`);
    }
    points.push({ period: row.period, value });
  }
  const recentMedian = median(points.slice(3));
  const priorMedian = median(points.slice(0, 3));
  const change = recentMedian - priorMedian;
  const latest = points[5].value;
  const previous = points[4].value;
  const latestChange = latest - previous;
  const latestMovement = latestChange >= 3
    ? previous <= priorMedian - 3 && Math.abs(latest - priorMedian) < 3 ? "Rebounding" : "Improving"
    : latestChange <= -3 ? "Weakening" : "Steady";
  return {
    label: change >= 3 ? "Accelerating" : change <= -3 ? "Decelerating" : "Stable",
    change, recentMedian, priorMedian, latestChange, latestMovement, points, reason: null,
  };
}

export function formatMomentumPp(value: number | null) {
  if (value == null) return "-";
  const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  return `${value > 0 ? "+" : ""}${number} pp`;
}

export function revenueMomentumDetail(momentum: RevenueGrowthMomentum) {
  if (momentum.change == null) return momentum.reason ?? "Needs six consecutive quarters with comparable revenue YoY growth.";
  const percent = (value: number | null) => `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value!)}%`;
  const points = momentum.points;
  return `${momentum.label}: median growth is ${percent(momentum.recentMedian)} (${points[3].period}–${points[5].period}), versus ${percent(momentum.priorMedian)} (${points[0].period}–${points[2].period}); ${formatMomentumPp(momentum.change)}. Latest quarter: ${momentum.latestMovement?.toLowerCase()}, ${formatMomentumPp(momentum.latestChange)} (${percent(points[4].value)} → ${percent(points[5].value)}).`;
}
