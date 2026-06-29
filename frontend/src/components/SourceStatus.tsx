import { memo, useMemo } from "react";
import type { RefreshJob, SourceSyncStatus } from "../api";

export type SummarizedSourceStatus = SourceSyncStatus & {
  label?: string;
};

type Props = {
  statuses: SummarizedSourceStatus[];
  activeJobs?: RefreshJob[];
  summarized?: boolean;
};

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const formatDate = (value?: string | null) => {
  if (!value) {
    return "Never";
  }
  return dateFormatter.format(new Date(value));
};

const SOURCE_GROUPS = [
  { key: "manual", label: "Manual cash and assets", sources: ["manual"] },
  { key: "binance", label: "Binance", sources: ["binance", "binance_ledger"] },
  { key: "ibkr", label: "IBKR", sources: ["ibkr", "ibkr_history"] },
  { key: "market_data", label: "Market prices", sources: ["market_data", "fx"] },
];

const STATUS_RANK: Record<string, number> = {
  error: 4,
  warning: 3,
  never: 2,
  success: 1,
};

const aggregateStatus = (items: SourceSyncStatus[]) => {
  if (items.length === 0) {
    return "never";
  }
  return items.reduce((current, item) => (
    (STATUS_RANK[item.status] ?? 2) > (STATUS_RANK[current] ?? 2) ? item.status : current
  ), "success");
};

const aggregateDate = (items: SourceSyncStatus[]) => {
  if (items.some((item) => !item.last_synced_at)) {
    return null;
  }
  return items
    .map((item) => item.last_synced_at)
    .filter(Boolean)
    .sort()[0] ?? null;
};

export const summarizeSourceStatuses = (statuses: SourceSyncStatus[]) => {
  const bySource = new Map(statuses.map((status) => [status.source, status]));
  const groupedKeys = new Set(SOURCE_GROUPS.flatMap((group) => group.sources));
  const grouped = SOURCE_GROUPS.map((group) => {
    const items = group.sources.map((source) => bySource.get(source)).filter(Boolean) as SourceSyncStatus[];
    return {
      source: group.key,
      label: group.label,
      status: aggregateStatus(items),
      last_synced_at: aggregateDate(items),
    };
  });
  const unknown = statuses
    .filter((status) => !groupedKeys.has(status.source))
    .map((status) => ({ ...status, label: status.source }));
  return [...grouped, ...unknown];
};

const isActiveRefreshJob = (job: RefreshJob) => job.status === "queued" || job.status === "running";

const formatElapsed = (seconds: number) => {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
};

const progressPercent = (job: RefreshJob) => {
  if (job.status === "queued") return 6;
  return Math.max(8, Math.min(96, (job.current_step / Math.max(1, job.total_steps)) * 100));
};

export const SourceStatus = memo(function SourceStatus({ statuses, activeJobs = [], summarized = false }: Props) {
  const rows = useMemo(
    () => (summarized ? statuses : summarizeSourceStatuses(statuses)),
    [statuses, summarized],
  );
  const visibleJobs = useMemo(() => activeJobs.filter(isActiveRefreshJob), [activeJobs]);

  return (
    <div className="source-status-content">
      {visibleJobs.length > 0 && (
        <div className="sync-active-jobs">
          {visibleJobs.map((job) => (
            <article className={`refresh-job ${job.status}`} key={job.id}>
              <div className="refresh-job-main">
                <div>
                  <strong>{job.label}</strong>
                  <span>{job.status === "queued" ? "Queued" : job.stage}</span>
                </div>
                <small>{`${formatElapsed(job.elapsed_seconds)} · ${job.current_step}/${job.total_steps}`}</small>
              </div>
              <div className="refresh-progress" aria-hidden="true">
                <span style={{ width: `${progressPercent(job)}%` }} />
              </div>
            </article>
          ))}
        </div>
      )}
      <div className="sync-list">
        {rows.map((status) => (
          <div className="sync-row" key={status.source}>
            <strong>{status.label ?? status.source}</strong>
            <span className={`sync-badge ${status.status}`}>{status.status}</span>
            <span>{formatDate(status.last_synced_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
});
