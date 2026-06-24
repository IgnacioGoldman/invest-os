import { AlertTriangle, Bot, Info, SendHorizontal, ShieldAlert, Sparkles, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import type { Recommendation, RecommendationFollowUpResponse } from "../api";
import { formatDateTime } from "../format";

type Props = {
  recommendations: Recommendation[];
  generatedAt?: string | null;
  latestSourceSyncedAt?: string | null;
  analyzing?: boolean;
  onAnalyze?: () => void;
  onAskRecommendation?: (recommendation: Recommendation, question: string) => Promise<RecommendationFollowUpResponse>;
  onLoadRecommendationFollowUps?: () => Promise<RecommendationFollowUpResponse[]>;
  onPollRecommendation?: (requestId: string) => Promise<RecommendationFollowUpResponse>;
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

function groupFollowUps(
  responses: RecommendationFollowUpResponse[],
  visibleKeys: Set<string>,
): Record<string, FollowUpTurn[]> {
  return responses.reduce<Record<string, FollowUpTurn[]>>((groups, response) => {
    if (!visibleKeys.has(response.recommendation_key)) {
      return groups;
    }
    groups[response.recommendation_key] = [
      ...(groups[response.recommendation_key] ?? []),
      { question: response.question, response },
    ];
    return groups;
  }, {});
}

export function Recommendations({
  recommendations,
  generatedAt,
  latestSourceSyncedAt,
  analyzing = false,
  onAnalyze,
  onAskRecommendation,
  onLoadRecommendationFollowUps,
  onPollRecommendation,
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
  const visibleRecommendationKeys = new Set(visibleRecommendations.map(recommendationKey));
  const visibleRecommendationKey = [...visibleRecommendationKeys].sort().join("|");
  const pendingFollowUpIds = Object.values(followUps)
    .flatMap((turns) => turns.map((turn) => turn.response))
    .filter((response) => response.status === "pending_codex" && response.follow_up_id)
    .map((response) => response.follow_up_id as string);
  const pendingFollowUpKey = [...new Set(pendingFollowUpIds)].sort().join("|");

  useEffect(() => {
    if (!onLoadRecommendationFollowUps) {
      return;
    }
    let cancelled = false;
    onLoadRecommendationFollowUps()
      .then((responses) => {
        if (cancelled) {
          return;
        }
        setFollowUps(groupFollowUps(responses, visibleRecommendationKeys));
      })
      .catch(() => {
        // The recommendation list should remain usable if thread hydration misses once.
      });
    return () => {
      cancelled = true;
    };
  }, [onLoadRecommendationFollowUps, visibleRecommendationKey]);

  useEffect(() => {
    if (!onPollRecommendation || !pendingFollowUpKey) {
      return;
    }
    let cancelled = false;
    const ids = pendingFollowUpKey.split("|");
    const poll = async () => {
      const results = await Promise.allSettled(ids.map((id) => onPollRecommendation(id)));
      if (cancelled) {
        return;
      }
      const completed = results
        .filter((result): result is PromiseFulfilledResult<RecommendationFollowUpResponse> => result.status === "fulfilled")
        .map((result) => result.value)
        .filter((response) => response.status === "complete" && response.follow_up_id);
      if (completed.length === 0) {
        return;
      }
      const completedById = new Map(completed.map((response) => [response.follow_up_id, response]));
      setFollowUps((threads) => {
        let changed = false;
        const next = Object.fromEntries(
          Object.entries(threads).map(([key, turns]) => [
            key,
            turns.map((turn) => {
              const replacement = turn.response.follow_up_id
                ? completedById.get(turn.response.follow_up_id)
                : undefined;
              if (!replacement) {
                return turn;
              }
              changed = true;
              return { ...turn, response: replacement };
            }),
          ]),
        );
        return changed ? next : threads;
      });
    };
    poll();
    const interval = window.setInterval(poll, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [onPollRecommendation, pendingFollowUpKey]);

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
      const responseKey = response.recommendation_key || key;
      setFollowUps((threads) => ({
        ...threads,
        [responseKey]: [...(threads[responseKey] ?? []), { question: response.question, response }],
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
                              <div
                                className="rec-follow-up-turn"
                                key={turn.response.follow_up_id ?? `${turn.response.generated_at}-${index}`}
                              >
                                <div className="rec-follow-up-message rec-follow-up-question">
                                  <span className="rec-chat-avatar" aria-hidden="true">
                                    <UserRound size={14} />
                                  </span>
                                  <div className="rec-chat-bubble">
                                    <div className="rec-chat-meta">
                                      <span>me</span>
                                    </div>
                                    <p>{turn.question}</p>
                                  </div>
                                </div>
                                <div className="rec-follow-up-message rec-follow-up-answer">
                                  <span className="rec-chat-avatar" aria-hidden="true">
                                    <Bot size={14} />
                                  </span>
                                  <div className="rec-chat-bubble">
                                    <div className="rec-chat-meta">
                                      <span>invest-os</span>
                                      <time dateTime={turn.response.generated_at}>
                                        {formatDateTime(turn.response.generated_at)}
                                      </time>
                                    </div>
                                    <p>{turn.response.answer}</p>
                                    {turn.response.status === "pending_codex" && (
                                      <small className="rec-follow-up-status">
                                        <span aria-hidden="true" />
                                        Waiting for Codex callback
                                      </small>
                                    )}
                                    {turn.response.codex_command && (
                                      <details className="rec-follow-up-command">
                                        <summary>Codex IDE prompt</summary>
                                        <pre>
                                          <code>{turn.response.codex_command}</code>
                                        </pre>
                                      </details>
                                    )}
                                  </div>
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
                            <textarea
                              value={draft}
                              onChange={(event) =>
                                setDrafts((current) => ({ ...current, [key]: event.target.value }))
                              }
                              onKeyDown={(event) => {
                                if (event.key === "Enter" && !event.shiftKey) {
                                  event.preventDefault();
                                  event.currentTarget.form?.requestSubmit();
                                }
                              }}
                              placeholder="Ask invest-os about this recommendation"
                              aria-label={`Ask about ${rec.title}`}
                              rows={1}
                            />
                            <button
                              type="submit"
                              disabled={isPending || !draft.trim()}
                              title={isPending ? "Waiting for Invest OS" : "Send question"}
                            >
                              <SendHorizontal size={16} aria-hidden="true" />
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
