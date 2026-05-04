import type { SourceSyncStatus } from "../api";

type Props = {
  statuses: SourceSyncStatus[];
};

const formatDate = (value?: string | null) => {
  if (!value) {
    return "Never";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
};

export function SourceStatus({ statuses }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Source Sync</h2>
      </div>
      <div className="sync-list">
        {statuses.map((status) => (
          <div className="sync-row" key={status.source}>
            <strong>{status.source}</strong>
            <span className={`sync-badge ${status.status}`}>{status.status}</span>
            <span>{formatDate(status.last_synced_at)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
