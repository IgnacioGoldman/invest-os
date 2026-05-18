import { AlertTriangle, Info, ShieldAlert } from "lucide-react";
import type { Recommendation } from "../api";

type Props = {
  recommendations: Recommendation[];
};

const ICON = {
  info: <Info size={16} />,
  warning: <AlertTriangle size={16} />,
  critical: <ShieldAlert size={16} />,
} as const;

export function Recommendations({ recommendations }: Props) {
  if (recommendations.length === 0) return null;

  return (
    <section className="panel recommendations">
      <div className="panel-heading">
        <h2>Recommendations</h2>
        <span>{recommendations.length}</span>
      </div>
      <ul className="rec-list">
        {recommendations.map((rec, i) => (
          <li key={i} className={`rec-item rec-${rec.severity}`}>
            <span className="rec-icon">{ICON[rec.severity]}</span>
            <div>
              <strong>{rec.title}</strong>
              <p>{rec.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
