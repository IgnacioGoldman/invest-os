import {
  AlertTriangle,
  ArchiveX,
  Bot,
  ChevronDown,
  Info,
  SendHorizontal,
  ShieldAlert,
  Sparkles,
  Undo2,
  UserRound,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
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

type RecommendationItemProps = {
  rec: Recommendation;
  recKey: string;
  chatId: string;
  thread: FollowUpTurn[];
  isPending: boolean;
  followUpError?: string;
  chatIsOpen: boolean;
  isDiscarded?: boolean;
  onAsk?: (recommendation: Recommendation, question: string) => Promise<boolean>;
  onDiscard?: (key: string) => void;
  onRestore?: (key: string) => void;
  onToggleChat: (key: string) => void;
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
  entry: "Entry candidates",
  concentration: "Concentration",
  theme: "Theme",
} as const;

const DISCARDED_RECOMMENDATIONS_STORAGE_KEY = "invest-os:discarded-recommendation-keys";

function loadDiscardedRecommendationKeys() {
  if (typeof window === "undefined") {
    return new Set<string>();
  }
  try {
    const raw = window.localStorage.getItem(DISCARDED_RECOMMENDATIONS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) {
      return new Set<string>();
    }
    return new Set(parsed.filter((key): key is string => typeof key === "string"));
  } catch {
    return new Set<string>();
  }
}

function saveDiscardedRecommendationKeys(keys: Set<string>) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(DISCARDED_RECOMMENDATIONS_STORAGE_KEY, JSON.stringify([...keys]));
  } catch {
    // Keep discard usable even if browser storage is unavailable.
  }
}

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

const RecommendationItem = memo(function RecommendationItem({
  rec,
  recKey,
  chatId,
  thread,
  isPending,
  followUpError,
  chatIsOpen,
  isDiscarded = false,
  onAsk,
  onDiscard,
  onRestore,
  onToggleChat,
}: RecommendationItemProps) {
  const [draft, setDraft] = useState("");
  const hasAsk = Boolean(onAsk);

  const askRecommendation = async (event: FormEvent) => {
    event.preventDefault();
    const question = draft.trim();
    if (!onAsk || !question) {
      return;
    }
    const didSend = await onAsk(rec, question);
    if (didSend) {
      setDraft("");
    }
  };

  return (
    <li className={`rec-item rec-${rec.severity}`}>
      <span className="rec-icon">{ICON[rec.severity]}</span>
      <div className="rec-content">
        <strong>{rec.title}</strong>
        <p>{rec.detail}</p>
        {isDiscarded ? (
          <div className="rec-discarded-actions">
            <button type="button" onClick={() => onRestore?.(recKey)} title="Restore recommendation">
              <Undo2 size={15} aria-hidden="true" />
              Restore
            </button>
          </div>
        ) : (
          <div className="rec-action-row">
            {(thread.length > 0 || hasAsk) && (
              <div className="rec-chat-dropdown">
                <button
                  type="button"
                  className="rec-chat-toggle"
                  aria-expanded={chatIsOpen}
                  aria-controls={chatId}
                  onClick={() => onToggleChat(recKey)}
                >
                  <span>
                    <Bot size={15} aria-hidden="true" />
                    {thread.length > 0 ? `Chat (${thread.length})` : "Ask follow-up"}
                  </span>
                  <ChevronDown size={16} aria-hidden="true" />
                </button>

                {chatIsOpen && (
                  <div className="rec-chat-panel" id={chatId}>
                    {thread.length > 0 && (
                      <div className="rec-follow-up-thread">
                        {thread.map((turn, turnIndex) => (
                          <div
                            className="rec-follow-up-turn"
                            key={turn.response.follow_up_id ?? `${turn.response.generated_at}-${turnIndex}`}
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
                    {followUpError && (
                      <p className="rec-follow-up-error" role="alert">
                        {followUpError}
                      </p>
                    )}
                    {onAsk && (
                      <form className="rec-follow-up-form" onSubmit={askRecommendation}>
                        <textarea
                          value={draft}
                          onChange={(event) => setDraft(event.target.value)}
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
                )}
              </div>
            )}
            <button
              type="button"
              className="rec-discard-button"
              onClick={() => onDiscard?.(recKey)}
              title="Discard recommendation"
            >
              <ArchiveX size={15} aria-hidden="true" />
              Discard
            </button>
          </div>
        )}
      </div>
    </li>
  );
});

export const Recommendations = memo(function Recommendations({
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
  const [followUps, setFollowUps] = useState<Record<string, FollowUpTurn[]>>({});
  const [openChatKeys, setOpenChatKeys] = useState<Record<string, boolean>>({});
  const [discardedKeys, setDiscardedKeys] = useState<Set<string>>(loadDiscardedRecommendationKeys);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [followUpErrors, setFollowUpErrors] = useState<Record<string, string>>({});
  const actionableRecommendations = useMemo(
    () => recommendations.filter((rec) => rec.severity !== "info"),
    [recommendations],
  );
  const visibleRecommendations = useMemo(
    () => actionableRecommendations.filter((rec) => !discardedKeys.has(recommendationKey(rec))),
    [actionableRecommendations, discardedKeys],
  );
  const discardedRecommendations = useMemo(
    () => actionableRecommendations.filter((rec) => discardedKeys.has(recommendationKey(rec))),
    [actionableRecommendations, discardedKeys],
  );
  const groupedRecommendations = useMemo(
    () =>
      visibleRecommendations.reduce<Record<string, Recommendation[]>>((groups, rec) => {
        const category = rec.category ?? "allocation";
        groups[category] = [...(groups[category] ?? []), rec];
        return groups;
      }, {}),
    [visibleRecommendations],
  );
  const shouldRerun = isSourceDataNewer(generatedAt, latestSourceSyncedAt);
  const visibleRecommendationKeys = useMemo(
    () => new Set(actionableRecommendations.map(recommendationKey)),
    [actionableRecommendations],
  );
  const visibleRecommendationKey = useMemo(
    () => [...visibleRecommendationKeys].sort().join("|"),
    [visibleRecommendationKeys],
  );
  const pendingFollowUpKey = useMemo(() => {
    const ids = Object.values(followUps)
      .flatMap((turns) => turns.map((turn) => turn.response))
      .filter((response) => response.status === "pending_codex" && response.follow_up_id)
      .map((response) => response.follow_up_id as string);
    return [...new Set(ids)].sort().join("|");
  }, [followUps]);

  useEffect(() => {
    saveDiscardedRecommendationKeys(discardedKeys);
  }, [discardedKeys]);

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
        const next = { ...threads };
        Object.entries(threads).forEach(([key, turns]) => {
          let threadChanged = false;
          const nextTurns = turns.map((turn) => {
            const replacement = turn.response.follow_up_id
              ? completedById.get(turn.response.follow_up_id)
              : undefined;
            if (!replacement) {
              return turn;
            }
            threadChanged = true;
            return { ...turn, response: replacement };
          });
          if (threadChanged) {
            next[key] = nextTurns;
            changed = true;
          }
        });
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

  const askRecommendation = useCallback(async (rec: Recommendation, question: string) => {
    if (!onAskRecommendation) {
      return false;
    }
    const key = recommendationKey(rec);
    setOpenChatKeys((current) => ({ ...current, [key]: true }));
    setPendingKey(key);
    setFollowUpErrors((errors) => ({ ...errors, [key]: "" }));
    try {
      const response = await onAskRecommendation(rec, question);
      const responseKey = response.recommendation_key || key;
      setOpenChatKeys((current) => ({ ...current, [key]: true, [responseKey]: true }));
      setFollowUps((threads) => ({
        ...threads,
        [responseKey]: [...(threads[responseKey] ?? []), { question: response.question, response }],
      }));
      return true;
    } catch (error) {
      setFollowUpErrors((errors) => ({
        ...errors,
        [key]: error instanceof Error ? error.message : "Could not analyze this recommendation.",
      }));
      return false;
    } finally {
      setPendingKey(null);
    }
  }, [onAskRecommendation]);

  const toggleChat = useCallback((key: string) => {
    setOpenChatKeys((current) => ({ ...current, [key]: !(current[key] ?? false) }));
  }, []);

  const discardRecommendation = useCallback((key: string) => {
    setDiscardedKeys((current) => new Set(current).add(key));
    setOpenChatKeys((current) => ({ ...current, [key]: false }));
  }, []);

  const restoreRecommendation = useCallback((key: string) => {
    setDiscardedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  }, []);

  if (actionableRecommendations.length === 0 && !onAnalyze && !alwaysShow) return null;

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
                {recs.map((rec, index) => {
                  const key = recommendationKey(rec);
                  const thread = followUps[key] ?? [];
                  const chatId = `rec-chat-${category.replace(/[^a-zA-Z0-9_-]/g, "-")}-${index}`;
                  return (
                    <RecommendationItem
                      key={key}
                      rec={rec}
                      recKey={key}
                      chatId={chatId}
                      thread={thread}
                      isPending={pendingKey === key}
                      followUpError={followUpErrors[key]}
                      chatIsOpen={openChatKeys[key] ?? false}
                      onAsk={onAskRecommendation ? askRecommendation : undefined}
                      onDiscard={discardRecommendation}
                      onToggleChat={toggleChat}
                    />
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty block">No active recommendations.</p>
      )}
      {discardedRecommendations.length > 0 && (
        <details className="rec-discarded-pile">
          <summary>
            <span>
              <ArchiveX size={15} aria-hidden="true" />
              Discarded recommendations
            </span>
            <strong>{discardedRecommendations.length}</strong>
          </summary>
          <ul className="rec-list rec-discarded-list">
            {discardedRecommendations.map((rec, index) => {
              const key = recommendationKey(rec);
              return (
                <RecommendationItem
                  key={key}
                  rec={rec}
                  recKey={key}
                  chatId={`rec-discarded-${index}`}
                  thread={followUps[key] ?? []}
                  isPending={false}
                  followUpError={followUpErrors[key]}
                  chatIsOpen={false}
                  isDiscarded
                  onRestore={restoreRecommendation}
                  onToggleChat={toggleChat}
                />
              );
            })}
          </ul>
        </details>
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
});
