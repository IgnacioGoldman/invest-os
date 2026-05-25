import { AlertTriangle, Info, ShieldAlert, Sparkles } from "lucide-react";
import type { Recommendation } from "../api";

type Props = {
  recommendations: Recommendation[];
  analyzing?: boolean;
  onAnalyze?: () => void;
};

const ICON = {
  info: <Info size={16} />,
  warning: <AlertTriangle size={16} />,
  critical: <ShieldAlert size={16} />,
} as const;

export function Recommendations({ recommendations, analyzing = false, onAnalyze }: Props) {
  const visibleRecommendations = recommendations.filter((rec) => rec.severity !== "info");

  if (visibleRecommendations.length === 0 && !onAnalyze) return null;

  return (
    <section className="panel recommendations">
      <div className="panel-heading">
        <h2>Recommendations</h2>
        <div className="panel-heading-actions">
          <span>{visibleRecommendations.length}</span>
          {onAnalyze && (
            <button type="button" onClick={onAnalyze} disabled={analyzing} title="Analyze portfolio with AI">
              <Sparkles size={16} aria-hidden="true" />
              {analyzing ? "Analyzing" : "Analyze Portfolio"}
            </button>
          )}
        </div>
      </div>
      {visibleRecommendations.length ? (
        <ul className="rec-list">
          {visibleRecommendations.map((rec, i) => (
            <li key={i} className={`rec-item rec-${rec.severity}`}>
              <span className="rec-icon">{ICON[rec.severity]}</span>
              <div>
                <strong>{rec.title}</strong>
                <p>{rec.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty block">No warning recommendations yet.</p>
      )}
    </section>
  );
}
