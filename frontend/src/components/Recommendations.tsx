import { AlertTriangle, Info, Send, ShieldAlert, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { Recommendation, RecommendationFollowUpResponse } from "../api";
import { formatDateTime } from "../format";

type Props = {
  recommendations: Recommendation[];
  generatedAt?: string | null;
  latestSourceSyncedAt?: string | null;
  analyzing?: boolean;
  onAnalyze?: () => void;
  onAskRecommendation?: (recommendation: Recommendation, question: string) => Promise<RecommendationFollowUpResponse>;
  alwaysShow?: boolean;
};

type FollowUpTurn = {
  question: string;
  response: RecommendationFollowUpResponse;
};

const ICON = {
  info: <Info size={16} />,
  warning: <AlertTriangle size={16} />,
  critical: <ShieldAlert size={16} />,
} as const;

const CATEGORY_LABEL = {
  allocation: "Allocation",
  drawdown_reserve: "Drawdown reserve",
  trim_or_exit: "Trim / exit",
  capital_move: "Capital move",
  entry: "Entry",
  concentration: "Concentration",
  theme: "Theme",
} as const;

function isSourceDataNewer(generatedAt?: string | null, latestSourceSyncedAt?: string | null) {
  if (!latestSourceSyncedAt) {
    return false;
  }
  if (!generatedAt) {
    return true;
  }
  return new Date(latestSourceSyncedAt).getTime() > new Date(generatedAt).getTime();
}

function recommendationKey(rec: Recommendation) {
  return `${rec.category}:${rec.severity}:${rec.title}:${rec.detail}`;
}

export function Recommendations({
  recommendations,
  generatedAt,
  latestSourceSyncedAt,
  analyzing = false,
  onAnalyze,
  onAskRecommendation,
  alwaysShow = false,
}: Props) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [followUps, setFollowUps] = useState<Record<string, FollowUpTurn[]>>({});
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [followUpErrors, setFollowUpErrors] = useState<Record<string, string>>({});
  const visibleRecommendations = recommendations.filter((rec) => rec.severity !== "info");
  const groupedRecommendations = visibleRecommendations.reduce<Record<string, Recommendation[]>>((groups, rec) => {
    const category = rec.category ?? "allocation";
    groups[category] = [...(groups[category] ?? []), rec];
    return groups;
  }, {});
  const shouldRerun = isSourceDataNewer(generatedAt, latestSourceSyncedAt);

  const askRecommendation = async (event: FormEvent, rec: Recommendation) => {
    event.preventDefault();
    if (!onAskRecommendation) {
      return;
    }
    const key = recommendationKey(rec);
    const question = (drafts[key] ?? "").trim();
    if (!question) {
      return;
    }
    setPendingKey(key);
    setFollowUpErrors((errors) => ({ ...errors, [key]: "" }));
    try {
      const response = await onAskRecommendation(rec, question);
      setFollowUps((threads) => ({
        ...threads,
        [key]: [...(threads[key] ?? []), { question, response }],
      }));
      setDrafts((current) => ({ ...current, [key]: "" }));
    } catch (error) {
      setFollowUpErrors((errors) => ({
        ...errors,
        [key]: error instanceof Error ? error.message : "Could not analyze this recommendation.",
      }));
    } finally {
      setPendingKey(null);
    }
  };

  if (visibleRecommendations.length === 0 && !onAnalyze && !alwaysShow) return null;

  return (
    <section className="panel recommendations">
      <div className="panel-heading">
        <h2>Recommendations</h2>
        <div className="panel-heading-actions">
          <small className="recommendations-run-time">
            Last run {generatedAt ? formatDateTime(generatedAt) : "never"}
          </small>
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
        <div className="rec-groups">
          {Object.entries(groupedRecommendations).map(([category, recs]) => (
            <div className="rec-group" key={category}>
              <h3>{CATEGORY_LABEL[category as keyof typeof CATEGORY_LABEL] ?? category}</h3>
              <ul className="rec-list">
                {recs.map((rec) => {
                  const key = recommendationKey(rec);
                  const draft = drafts[key] ?? "";
                  const thread = followUps[key] ?? [];
                  const isPending = pendingKey === key;
                  return (
                    <li key={key} className={`rec-item rec-${rec.severity}`}>
                      <span className="rec-icon">{ICON[rec.severity]}</span>
                      <div className="rec-content">
                        <strong>{rec.title}</strong>
                        <p>{rec.detail}</p>
                        {thread.length > 0 && (
                          <div className="rec-follow-up-thread">
                            {thread.map((turn, index) => (
                              <div className="rec-follow-up-turn" key={`${turn.response.generated_at}-${index}`}>
                                <div className="rec-follow-up-message rec-follow-up-question">
                                  <span>me</span>
                                  <p>{turn.question}</p>
                                </div>
                                <div className="rec-follow-up-message rec-follow-up-answer">
                                  <span>invest-os{turn.response.mode === "local" ? " local" : ""}</span>
                                  <p>{turn.response.answer}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        {followUpErrors[key] && (
                          <p className="rec-follow-up-error" role="alert">
                            {followUpErrors[key]}
                          </p>
                        )}
                        {onAskRecommendation && (
                          <form className="rec-follow-up-form" onSubmit={(event) => askRecommendation(event, rec)}>
                            <input
                              value={draft}
                              onChange={(event) =>
                                setDrafts((current) => ({ ...current, [key]: event.target.value }))
                              }
                              placeholder="Ask about this recommendation"
                              aria-label={`Ask about ${rec.title}`}
                            />
                            <button
                              type="submit"
                              disabled={isPending || !draft.trim()}
                              title="Analyze this recommendation"
                            >
                              <Send size={15} aria-hidden="true" />
                              {isPending ? "Thinking" : "Ask"}
                            </button>
                          </form>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty block">No warning recommendations yet.</p>
      )}
      {shouldRerun && (
        <div className="recommendations-stale-alert" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <div>
            <strong>New portfolio data is available.</strong>
            <p>
              Analyze Portfolio should be run again. Last run{" "}
              {generatedAt ? formatDateTime(generatedAt) : "never"}
              {latestSourceSyncedAt ? `; latest source sync ${formatDateTime(latestSourceSyncedAt)}.` : "."}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
