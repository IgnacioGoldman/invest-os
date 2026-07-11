import {
  AlertTriangle,
  ArchiveX,
  Bot,
  Check,
  Info,
  MessageSquare,
  RotateCcw,
  SendHorizontal,
  ShieldAlert,
  Sparkles,
  Undo2,
  UserRound,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
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

type RecommendationTab = "working" | "accepted" | "discarded";

type RecommendationRecord = {
  key: string;
  rec: Recommendation;
  status: RecommendationTab;
  thread: FollowUpTurn[];
};

const EMPTY_THREAD: FollowUpTurn[] = [];
const DISCARDED_RECOMMENDATIONS_STORAGE_KEY = "invest-os:discarded-recommendation-keys";
const ACCEPTED_RECOMMENDATIONS_STORAGE_KEY = "invest-os:accepted-recommendation-keys";

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

function loadStoredKeys(storageKey: string) {
  if (typeof window === "undefined") {
    return new Set<string>();
  }
  try {
    const raw = window.localStorage.getItem(storageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) {
      return new Set<string>();
    }
    return new Set(parsed.filter((key): key is string => typeof key === "string"));
  } catch {
    return new Set<string>();
  }
}

function saveStoredKeys(storageKey: string, keys: Set<string>) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(storageKey, JSON.stringify([...keys]));
  } catch {
    // Keep the UI usable even if browser storage is unavailable.
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

function statusForKey(key: string, acceptedKeys: Set<string>, discardedKeys: Set<string>): RecommendationTab {
  if (discardedKeys.has(key)) {
    return "discarded";
  }
  if (acceptedKeys.has(key)) {
    return "accepted";
  }
  return "working";
}

function tabLabel(tab: RecommendationTab) {
  if (tab === "working") return "Working";
  if (tab === "accepted") return "Accepted";
  return "Discarded";
}

function categoryLabel(rec: Recommendation) {
  return CATEGORY_LABEL[rec.category] ?? rec.category;
}

function severityLabel(severity: Recommendation["severity"]) {
  if (severity === "critical") return "High priority";
  if (severity === "warning") return "Watch";
  return "Info";
}

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
  const [tab, setTab] = useState<RecommendationTab>("working");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [followUps, setFollowUps] = useState<Record<string, FollowUpTurn[]>>({});
  const [acceptedKeys, setAcceptedKeys] = useState<Set<string>>(() =>
    loadStoredKeys(ACCEPTED_RECOMMENDATIONS_STORAGE_KEY),
  );
  const [discardedKeys, setDiscardedKeys] = useState<Set<string>>(() =>
    loadStoredKeys(DISCARDED_RECOMMENDATIONS_STORAGE_KEY),
  );
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [followUpErrors, setFollowUpErrors] = useState<Record<string, string>>({});
  const scrollRef = useRef<HTMLDivElement>(null);

  const actionableRecommendations = useMemo(
    () => recommendations.filter((rec) => rec.severity !== "info"),
    [recommendations],
  );
  const visibleRecommendationKeys = useMemo(
    () => new Set(actionableRecommendations.map(recommendationKey)),
    [actionableRecommendations],
  );
  const visibleRecommendationKey = useMemo(
    () => [...visibleRecommendationKeys].sort().join("|"),
    [visibleRecommendationKeys],
  );
  const records = useMemo<RecommendationRecord[]>(
    () =>
      actionableRecommendations.map((rec) => {
        const key = recommendationKey(rec);
        return {
          key,
          rec,
          status: statusForKey(key, acceptedKeys, discardedKeys),
          thread: followUps[key] ?? EMPTY_THREAD,
        };
      }),
    [acceptedKeys, actionableRecommendations, discardedKeys, followUps],
  );
  const filteredRecords = useMemo(
    () => records.filter((record) => record.status === tab),
    [records, tab],
  );
  const activeRecord = useMemo(
    () => records.find((record) => record.key === activeKey) ?? null,
    [activeKey, records],
  );
  const activeThread = activeRecord?.thread ?? EMPTY_THREAD;
  const activeError = activeRecord ? followUpErrors[activeRecord.key] : undefined;
  const counts = useMemo(
    () => ({
      working: records.filter((record) => record.status === "working").length,
      accepted: records.filter((record) => record.status === "accepted").length,
      discarded: records.filter((record) => record.status === "discarded").length,
    }),
    [records],
  );
  const shouldRerun = isSourceDataNewer(generatedAt, latestSourceSyncedAt);
  const pendingFollowUpKey = useMemo(() => {
    const ids = Object.values(followUps)
      .flatMap((turns) => turns.map((turn) => turn.response))
      .filter((response) => response.status === "pending_codex" && response.follow_up_id)
      .map((response) => response.follow_up_id as string);
    return [...new Set(ids)].sort().join("|");
  }, [followUps]);

  useEffect(() => {
    saveStoredKeys(ACCEPTED_RECOMMENDATIONS_STORAGE_KEY, acceptedKeys);
  }, [acceptedKeys]);

  useEffect(() => {
    saveStoredKeys(DISCARDED_RECOMMENDATIONS_STORAGE_KEY, discardedKeys);
  }, [discardedKeys]);

  useEffect(() => {
    if (activeKey && filteredRecords.some((record) => record.key === activeKey)) {
      return;
    }
    setActiveKey(filteredRecords[0]?.key ?? null);
  }, [activeKey, filteredRecords]);

  useEffect(() => {
    setDraft("");
  }, [activeKey]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [activeKey, activeThread.length, pendingKey]);

  useEffect(() => {
    if (!onLoadRecommendationFollowUps) {
      return;
    }
    let cancelled = false;
    onLoadRecommendationFollowUps()
      .then((responses) => {
        if (!cancelled) {
          setFollowUps(groupFollowUps(responses, visibleRecommendationKeys));
        }
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

  const acceptRecommendation = useCallback((key: string) => {
    setAcceptedKeys((current) => new Set(current).add(key));
    setDiscardedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    setTab("accepted");
    setActiveKey(key);
  }, []);

  const discardRecommendation = useCallback((key: string) => {
    setDiscardedKeys((current) => new Set(current).add(key));
    setAcceptedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    setTab("discarded");
    setActiveKey(key);
  }, []);

  const restoreRecommendation = useCallback((key: string) => {
    setDiscardedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    setAcceptedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    setTab("working");
    setActiveKey(key);
  }, []);

  const askRecommendation = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (!onAskRecommendation || !activeRecord) {
      return;
    }
    const question = draft.trim();
    if (!question) {
      return;
    }
    const key = activeRecord.key;
    setDraft("");
    setPendingKey(key);
    setFollowUpErrors((errors) => ({ ...errors, [key]: "" }));
    try {
      const response = await onAskRecommendation(activeRecord.rec, question);
      const responseKey = response.recommendation_key || key;
      setFollowUps((threads) => ({
        ...threads,
        [responseKey]: [...(threads[responseKey] ?? []), { question: response.question, response }],
      }));
    } catch (error) {
      setFollowUpErrors((errors) => ({
        ...errors,
        [key]: error instanceof Error ? error.message : "Could not analyze this recommendation.",
      }));
    } finally {
      setPendingKey(null);
    }
  }, [activeRecord, draft, onAskRecommendation]);

  if (actionableRecommendations.length === 0 && !onAnalyze && !alwaysShow) return null;

  return (
    <div className="advice-shell recommendations">
      <header className="advice-hero">
        <div>
          <h2>Recommendations</h2>
          <p>Review portfolio advice, keep what you accept, discard the noise, and ask follow-up questions in context.</p>
        </div>
        <div className="advice-run-card">
          <span>Last run</span>
          <strong>{generatedAt ? formatDateTime(generatedAt) : "Never"}</strong>
          {onAnalyze && (
            <button type="button" onClick={onAnalyze} disabled={analyzing} title="Analyze portfolio with AI">
              <Sparkles size={16} aria-hidden="true" />
              {analyzing ? "Analyzing" : "Analyze"}
            </button>
          )}
        </div>
      </header>

      {shouldRerun && (
        <div className="recommendations-stale-alert advice-stale-alert" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <div>
            <strong>New portfolio data is available.</strong>
            <p>
              Analyze should be run again. Last run {generatedAt ? formatDateTime(generatedAt) : "never"}
              {latestSourceSyncedAt ? `; latest source sync ${formatDateTime(latestSourceSyncedAt)}.` : "."}
            </p>
          </div>
        </div>
      )}

      <div className="advice-workspace">
        <aside className="advice-sidebar" aria-label="Recommendations">
          <div className="advice-sidebar-heading">
            <div>
              <strong>Inbox</strong>
              <span>{records.length} items</span>
            </div>
            {onAnalyze && (
              <button type="button" onClick={onAnalyze} disabled={analyzing} title="Run a new recommendation analysis">
                <Sparkles size={15} aria-hidden="true" />
                New run
              </button>
            )}
          </div>

          <div className="advice-tab-list" role="tablist" aria-label="Recommendation status">
            {(["working", "accepted", "discarded"] as RecommendationTab[]).map((item) => (
              <TabButton
                key={item}
                active={tab === item}
                count={counts[item]}
                label={tabLabel(item)}
                onClick={() => setTab(item)}
              />
            ))}
          </div>

          <div className="advice-rec-list">
            {filteredRecords.length === 0 ? (
              <div className="advice-list-empty">
                {tab === "working" ? "No working recommendations. Run a fresh analysis when you are ready." : `Nothing ${tabLabel(tab).toLowerCase()} yet.`}
              </div>
            ) : (
              filteredRecords.map((record) => (
                <button
                  type="button"
                  className={`advice-rec-button ${activeKey === record.key ? "active" : ""}`}
                  key={record.key}
                  onClick={() => setActiveKey(record.key)}
                  aria-pressed={activeKey === record.key}
                >
                  <span className={`advice-rec-severity severity-${record.rec.severity}`}>{ICON[record.rec.severity]}</span>
                  <span>
                    <strong>{record.rec.title}</strong>
                    <small>
                      <MessageSquare size={12} aria-hidden="true" />
                      {record.thread.length}
                      <em>{categoryLabel(record.rec)}</em>
                    </small>
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="advice-pane">
          {!activeRecord ? (
            <div className="advice-empty-state">
              <span className="advice-empty-icon">
                <Sparkles size={22} aria-hidden="true" />
              </span>
              <strong>{records.length ? "Pick a recommendation" : "No recommendations yet"}</strong>
              <p>
                {records.length
                  ? "Select an item from the inbox to review the reasoning and ask questions."
                  : "Run an analysis to create your first recommendation set."}
              </p>
              {onAnalyze && (
                <button type="button" onClick={onAnalyze} disabled={analyzing}>
                  <Sparkles size={16} aria-hidden="true" />
                  {analyzing ? "Analyzing" : "Analyze portfolio"}
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="advice-pane-header">
                <div className="advice-title-block">
                  <small>{categoryLabel(activeRecord.rec)}</small>
                  <div className="advice-title-row">
                    <h3>{activeRecord.rec.title}</h3>
                    <StatusBadge status={activeRecord.status} severity={activeRecord.rec.severity} />
                  </div>
                  <p>{activeRecord.rec.detail}</p>
                </div>

                <div className="advice-action-row">
                  {activeRecord.status !== "accepted" && (
                    <button
                      type="button"
                      className="advice-action-button accept"
                      onClick={() => acceptRecommendation(activeRecord.key)}
                    >
                      <Check size={15} aria-hidden="true" />
                      Accept
                    </button>
                  )}
                  {activeRecord.status !== "discarded" && (
                    <button
                      type="button"
                      className="advice-action-button discard"
                      onClick={() => discardRecommendation(activeRecord.key)}
                    >
                      <ArchiveX size={15} aria-hidden="true" />
                      Discard
                    </button>
                  )}
                  {activeRecord.status !== "working" && (
                    <button
                      type="button"
                      className="advice-action-button restore"
                      onClick={() => restoreRecommendation(activeRecord.key)}
                    >
                      {activeRecord.status === "discarded" ? <Undo2 size={15} aria-hidden="true" /> : <RotateCcw size={15} aria-hidden="true" />}
                      Working
                    </button>
                  )}
                </div>

                <div className="advice-context-card">
                  <strong>Why this matters</strong>
                  <p>
                    This is a {severityLabel(activeRecord.rec.severity).toLowerCase()} {categoryLabel(activeRecord.rec).toLowerCase()} item.
                    Use the chat below to test assumptions before acting.
                  </p>
                </div>
              </div>

              <div className="advice-chat-body" ref={scrollRef}>
                {activeThread.length === 0 && (
                  <div className="advice-chat-empty">
                    Ask anything about this recommendation, for example: "Why this now?", "What is the safer version?", or "What changes if I add cash?"
                  </div>
                )}
                {activeThread.map((turn, index) => (
                  <div className="advice-chat-turn" key={turn.response.follow_up_id ?? `${turn.response.generated_at}-${index}`}>
                    <div className="advice-chat-message user">
                      <span className="advice-chat-avatar" aria-hidden="true">
                        <UserRound size={14} />
                      </span>
                      <div className="advice-chat-bubble">
                        <div className="advice-chat-meta">
                          <span>me</span>
                        </div>
                        <p>{turn.question}</p>
                      </div>
                    </div>
                    <div className="advice-chat-message assistant">
                      <span className="advice-chat-avatar" aria-hidden="true">
                        <Bot size={14} />
                      </span>
                      <div className="advice-chat-bubble">
                        <div className="advice-chat-meta">
                          <span>invest-os</span>
                          <time dateTime={turn.response.generated_at}>{formatDateTime(turn.response.generated_at)}</time>
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
                {pendingKey === activeRecord.key && (
                  <div className="advice-thinking">
                    <Sparkles size={14} aria-hidden="true" />
                    Thinking...
                  </div>
                )}
                {activeError && (
                  <div className="advice-follow-up-error" role="alert">
                    {activeError}
                  </div>
                )}
              </div>

              {onAskRecommendation && activeRecord.status !== "discarded" && (
                <form className="advice-composer" onSubmit={askRecommendation}>
                  <div className="advice-composer-box">
                    <textarea
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          event.currentTarget.form?.requestSubmit();
                        }
                      }}
                      placeholder={`Ask about "${activeRecord.rec.title}"...`}
                      aria-label={`Ask about ${activeRecord.rec.title}`}
                      rows={1}
                    />
                    <button
                      type="submit"
                      disabled={pendingKey === activeRecord.key || !draft.trim()}
                      title={pendingKey === activeRecord.key ? "Waiting for Invest OS" : "Send question"}
                    >
                      <SendHorizontal size={17} aria-hidden="true" />
                    </button>
                  </div>
                  <p>Educational only, not financial advice.</p>
                </form>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
});

function TabButton({
  active,
  count,
  label,
  onClick,
}: {
  active: boolean;
  count: number;
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`advice-tab-button ${active ? "active" : ""}`} onClick={onClick}>
      {label}
      <span>{count}</span>
    </button>
  );
}

function StatusBadge({
  status,
  severity,
}: {
  status: RecommendationTab;
  severity: Recommendation["severity"];
}) {
  const Icon = status === "accepted" ? Check : status === "discarded" ? ArchiveX : Sparkles;
  const label = status === "working" ? severityLabel(severity) : tabLabel(status);
  return (
    <span className={`advice-status-badge status-${status} severity-${severity}`}>
      <Icon size={12} aria-hidden="true" />
      {label}
    </span>
  );
}
