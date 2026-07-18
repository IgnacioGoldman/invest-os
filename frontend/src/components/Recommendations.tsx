import {
  AlertTriangle,
  ArchiveX,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Info,
  ListChecks,
  MessageSquare,
  PieChart,
  RotateCcw,
  SendHorizontal,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Trash2,
  Undo2,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { Recommendation, RecommendationFollowUpResponse } from "../api";
import allocationPrompt from "../content/recommendation-prompts/allocation.md?raw";
import buyPrompt from "../content/recommendation-prompts/buy.md?raw";
import sellPrompt from "../content/recommendation-prompts/sell.md?raw";
import { formatDateTime } from "../format";

type Props = {
  recommendations: Recommendation[];
  generatedAt?: string | null;
  latestSourceSyncedAt?: string | null;
  onAskRecommendation?: (recommendation: Recommendation, question: string) => Promise<RecommendationFollowUpResponse>;
  onCreateCodexRecommendation?: (
    recommendation: Recommendation,
    question: string,
    prompt: string,
  ) => Promise<RecommendationFollowUpResponse>;
  onDeleteRecommendation?: (recommendation: Recommendation) => Promise<void>;
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

type RecommendationSummary = {
  headline: string;
  bullets: string[];
  source: "ai" | "pending" | "fallback";
};

type AnalysisWorkflow = "allocation" | "buy" | "sell";

type LocalRecommendation = {
  id: string;
  kind: AnalysisWorkflow;
  createdAt: string;
  recommendation: Recommendation;
};

const EMPTY_THREAD: FollowUpTurn[] = [];
const DISCARDED_RECOMMENDATIONS_STORAGE_KEY = "invest-os:discarded-recommendation-keys";
const ACCEPTED_RECOMMENDATIONS_STORAGE_KEY = "invest-os:accepted-recommendation-keys";
const DELETED_RECOMMENDATIONS_STORAGE_KEY = "invest-os:deleted-recommendation-keys";
const LOCAL_RECOMMENDATIONS_STORAGE_KEY = "invest-os:local-codex-recommendations";

const WORKFLOW_ORDER: AnalysisWorkflow[] = ["allocation", "buy", "sell"];

const WORKFLOW_OPTIONS: Record<AnalysisWorkflow, {
  label: string;
  description: string;
  icon: LucideIcon;
  severity: Recommendation["severity"];
  category: Recommendation["category"];
  title: string;
  detail: string;
  prompt: string;
}> = {
  allocation: {
    label: "Allocation",
    description: "Portfolio mix, reserves, concentration, and next action.",
    icon: PieChart,
    severity: "warning",
    category: "allocation",
    title: "Allocation Review",
    detail: "Allocation workflow ready.",
    prompt: allocationPrompt.trim(),
  },
  buy: {
    label: "Buy",
    description: "Find one accumulation idea and one tactical entry setup.",
    icon: TrendingUp,
    severity: "warning",
    category: "entry",
    title: "Buy Candidate Search",
    detail: "Buy workflow ready.",
    prompt: buyPrompt.trim(),
  },
  sell: {
    label: "Sell",
    description: "Audit current holdings for trim, exit, and watchlist risk.",
    icon: TrendingDown,
    severity: "critical",
    category: "trim_or_exit",
    title: "Sell / Trim Review",
    detail: "Sell workflow ready.",
    prompt: sellPrompt.trim(),
  },
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

function isAnalysisWorkflow(value: unknown): value is AnalysisWorkflow {
  return typeof value === "string" && WORKFLOW_ORDER.includes(value as AnalysisWorkflow);
}

function loadLocalRecommendations() {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(LOCAL_RECOMMENDATIONS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.flatMap((item): LocalRecommendation[] => {
      if (
        typeof item?.id !== "string" ||
        !isAnalysisWorkflow(item?.kind) ||
        typeof item?.createdAt !== "string" ||
        typeof item?.recommendation?.severity !== "string" ||
        typeof item?.recommendation?.category !== "string" ||
        typeof item?.recommendation?.title !== "string" ||
        typeof item?.recommendation?.detail !== "string"
      ) {
        return [];
      }
      return [{
        id: item.id,
        kind: item.kind,
        createdAt: item.createdAt,
        recommendation: {
          ...item.recommendation,
          id: typeof item.recommendation.id === "string" ? item.recommendation.id : undefined,
        },
      }];
    });
  } catch {
    return [];
  }
}

function saveLocalRecommendations(items: LocalRecommendation[]) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(LOCAL_RECOMMENDATIONS_STORAGE_KEY, JSON.stringify(items.slice(0, 25)));
  } catch {
    // Local prompts are convenience state; the app should remain usable if storage fails.
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
  if (rec.id) {
    return `id:${rec.id}`;
  }
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

function recommendationTitle(rec: Recommendation) {
  if (rec.title === "Codex allocation review") return "Allocation Review";
  if (rec.title === "Codex buy candidate search") return "Buy Candidate Search";
  if (rec.title === "Codex sell / trim review") return "Sell / Trim Review";
  return rec.title.replace(/^Codex\s+/i, "");
}

function cleanSummaryText(value: string) {
  return value
    .replace(/^[-*\d.\s]+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitSentences(value: string) {
  return value
    .replace(/\s+/g, " ")
    .split(/(?:\.\s+|\?\s+|!\s+)/)
    .map(cleanSummaryText)
    .filter(Boolean);
}

function firstSentence(value: string) {
  return splitSentences(value)[0] ?? cleanSummaryText(value);
}

function sectionAfter(label: string, answer: string) {
  const match = answer.match(new RegExp(`${label}:\\s*([\\s\\S]*?)(?:\\n\\n|$)`, "i"));
  return match?.[1]?.trim() ?? "";
}

function extractNumberedActions(answer: string) {
  const actions = sectionAfter("Recommended actions", answer);
  if (!actions) {
    return [];
  }
  return actions
    .split(/\s+(?=\d+\.\s+)/)
    .map((item) => item.replace(/^Recommended actions:\s*/i, ""))
    .map(cleanSummaryText)
    .filter(Boolean);
}

function extractMarkdownBullets(answer: string) {
  return answer
    .split("\n")
    .map((line) => line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)$/)?.[1] ?? "")
    .map(cleanSummaryText)
    .filter(Boolean);
}

function extractSummaryBullets(answer: string) {
  const actions = extractNumberedActions(answer);
  if (actions.length > 0) {
    return actions.slice(0, 4);
  }
  const markdownBullets = extractMarkdownBullets(answer);
  if (markdownBullets.length > 0) {
    return markdownBullets.slice(0, 4);
  }
  return splitSentences(answer).slice(0, 4);
}

function latestCompletedResponse(thread: FollowUpTurn[]) {
  return [...thread].reverse().find((turn) => turn.response.status === "complete" && turn.response.answer.trim())?.response ?? null;
}

function latestPendingResponse(thread: FollowUpTurn[]) {
  return [...thread].reverse().find((turn) => turn.response.status === "pending_codex")?.response ?? null;
}

function buildRecommendationSummary(record: RecommendationRecord): RecommendationSummary {
  const completed = latestCompletedResponse(record.thread);
  if (completed) {
    const mainDiagnosis = sectionAfter("Main diagnosis", completed.answer);
    const bottomLine = sectionAfter("Bottom line", completed.answer);
    const headline = firstSentence(mainDiagnosis || bottomLine || completed.answer);
    return {
      headline,
      bullets: extractSummaryBullets(completed.answer),
      source: "ai",
    };
  }
  if (latestPendingResponse(record.thread)) {
    return {
      headline: "Waiting for the Codex result.",
      bullets: [
        "Copy the prompt from chat if you have not run it yet.",
        "This summary updates when the callback arrives.",
      ],
      source: "pending",
    };
  }
  return {
    headline: "Ready for analysis.",
    bullets: [
      "Open chat to copy the Codex prompt.",
      "Accept, discard, or ask a follow-up once the answer is back.",
    ],
    source: "fallback",
  };
}

function createWorkflowRecommendation(kind: AnalysisWorkflow): LocalRecommendation {
  const option = WORKFLOW_OPTIONS[kind];
  const createdAt = new Date().toISOString();
  const id = `${kind}-${createdAt}-${Math.random().toString(36).slice(2, 8)}`;
  const recommendation: Recommendation = {
    id,
    severity: option.severity,
    category: option.category,
    title: option.title,
    detail: option.detail,
  };
  return {
    id,
    kind,
    createdAt,
    recommendation,
  };
}

export const Recommendations = memo(function Recommendations({
  recommendations,
  generatedAt,
  latestSourceSyncedAt,
  onAskRecommendation,
  onCreateCodexRecommendation,
  onDeleteRecommendation,
  onLoadRecommendationFollowUps,
  onPollRecommendation,
  alwaysShow = false,
}: Props) {
  const [tab, setTab] = useState<RecommendationTab>("working");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [analysisPickerOpen, setAnalysisPickerOpen] = useState(false);
  const [localRecommendations, setLocalRecommendations] = useState<LocalRecommendation[]>(loadLocalRecommendations);
  const [draft, setDraft] = useState("");
  const [followUps, setFollowUps] = useState<Record<string, FollowUpTurn[]>>({});
  const [acceptedKeys, setAcceptedKeys] = useState<Set<string>>(() =>
    loadStoredKeys(ACCEPTED_RECOMMENDATIONS_STORAGE_KEY),
  );
  const [discardedKeys, setDiscardedKeys] = useState<Set<string>>(() =>
    loadStoredKeys(DISCARDED_RECOMMENDATIONS_STORAGE_KEY),
  );
  const [deletedKeys, setDeletedKeys] = useState<Set<string>>(() =>
    loadStoredKeys(DELETED_RECOMMENDATIONS_STORAGE_KEY),
  );
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [startingWorkflow, setStartingWorkflow] = useState<AnalysisWorkflow | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [followUpErrors, setFollowUpErrors] = useState<Record<string, string>>({});
  const [expandedThreadKeys, setExpandedThreadKeys] = useState<Set<string>>(() => new Set());
  const scrollRef = useRef<HTMLDivElement>(null);
  const analysisMenuRef = useRef<HTMLDivElement>(null);

  const actionableRecommendations = useMemo(
    () => [
      ...localRecommendations.map((item) => item.recommendation),
      ...recommendations.filter((rec) => rec.severity !== "info"),
    ].filter((rec) => !deletedKeys.has(recommendationKey(rec))),
    [deletedKeys, localRecommendations, recommendations],
  );
  const localRecommendationKeys = useMemo(
    () => new Set(localRecommendations.map((item) => recommendationKey(item.recommendation))),
    [localRecommendations],
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
  const activeSummary = useMemo(
    () => activeRecord ? buildRecommendationSummary(activeRecord) : null,
    [activeRecord],
  );
  const activeThreadExpanded = activeRecord ? expandedThreadKeys.has(activeRecord.key) : false;
  const activeError = activeRecord ? followUpErrors[activeRecord.key] : undefined;
  const counts = useMemo(
    () => ({
      working: records.filter((record) => record.status === "working").length,
      accepted: records.filter((record) => record.status === "accepted").length,
      discarded: records.filter((record) => record.status === "discarded").length,
    }),
    [records],
  );
  const latestAnalysisAt = localRecommendations[0]?.createdAt ?? generatedAt ?? null;
  const shouldRerun = isSourceDataNewer(latestAnalysisAt, latestSourceSyncedAt);
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
    saveStoredKeys(DELETED_RECOMMENDATIONS_STORAGE_KEY, deletedKeys);
  }, [deletedKeys]);

  useEffect(() => {
    saveLocalRecommendations(localRecommendations);
  }, [localRecommendations]);

  useEffect(() => {
    if (!analysisPickerOpen) {
      return;
    }
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (analysisMenuRef.current?.contains(event.target as Node)) {
        return;
      }
      setAnalysisPickerOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAnalysisPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [analysisPickerOpen]);

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
    if (activeThreadExpanded) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [activeKey, activeThread.length, pendingKey, activeThreadExpanded]);

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

  const startWorkflowRecommendation = useCallback(async (kind: AnalysisWorkflow) => {
    const item = createWorkflowRecommendation(kind);
    const option = WORKFLOW_OPTIONS[kind];
    const key = recommendationKey(item.recommendation);
    const question = `Start ${option.label.toLowerCase()} recommendation workflow.`;
    setLocalRecommendations((current) => [item, ...current]);
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
    setDeletedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    setTab("working");
    setActiveKey(key);
    setAnalysisPickerOpen(false);
    setFollowUpErrors((errors) => ({ ...errors, [key]: "" }));
    if (!onCreateCodexRecommendation) {
      setFollowUpErrors((errors) => ({
        ...errors,
        [key]: "Could not create a Codex callback request.",
      }));
      return;
    }
    setStartingWorkflow(kind);
    setPendingKey(key);
    try {
      const response = await onCreateCodexRecommendation(item.recommendation, question, option.prompt);
      const responseKey = response.recommendation_key || key;
      setFollowUps((threads) => ({
        ...threads,
        [responseKey]: [...(threads[responseKey] ?? []), { question: response.question, response }],
      }));
    } catch (error) {
      setFollowUpErrors((errors) => ({
        ...errors,
        [key]: error instanceof Error ? error.message : "Could not create a Codex callback request.",
      }));
    } finally {
      setStartingWorkflow(null);
      setPendingKey((current) => (current === key ? null : current));
    }
  }, [onCreateCodexRecommendation]);

  const moveToNextRecordInCurrentTab = useCallback((key: string) => {
    setActiveKey((current) => {
      if (current !== key) {
        return current;
      }
      return filteredRecords.find((record) => record.key !== key)?.key ?? null;
    });
  }, [filteredRecords]);

  const acceptRecommendation = useCallback((key: string) => {
    setAcceptedKeys((current) => new Set(current).add(key));
    setDiscardedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    moveToNextRecordInCurrentTab(key);
  }, [moveToNextRecordInCurrentTab]);

  const discardRecommendation = useCallback((key: string) => {
    setDiscardedKeys((current) => new Set(current).add(key));
    setAcceptedKeys((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
    moveToNextRecordInCurrentTab(key);
  }, [moveToNextRecordInCurrentTab]);

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
    moveToNextRecordInCurrentTab(key);
  }, [moveToNextRecordInCurrentTab]);

  const deleteDiscardedRecommendation = useCallback(async (record: RecommendationRecord) => {
    if (!window.confirm(`Permanently delete "${recommendationTitle(record.rec)}"?`)) {
      return;
    }
    const isLocalRecommendation = localRecommendationKeys.has(record.key);
    setDeletingKey(record.key);
    try {
      if (!isLocalRecommendation && onDeleteRecommendation) {
        await onDeleteRecommendation(record.rec);
      }
      setLocalRecommendations((current) =>
        current.filter((item) => recommendationKey(item.recommendation) !== record.key),
      );
      setDeletedKeys((current) => new Set(current).add(record.key));
      setDiscardedKeys((current) => {
        const next = new Set(current);
        next.delete(record.key);
        return next;
      });
      setAcceptedKeys((current) => {
        const next = new Set(current);
        next.delete(record.key);
        return next;
      });
      setFollowUps((threads) => {
        const next = { ...threads };
        delete next[record.key];
        return next;
      });
      setFollowUpErrors((errors) => {
        const next = { ...errors };
        delete next[record.key];
        return next;
      });
      moveToNextRecordInCurrentTab(record.key);
    } finally {
      setDeletingKey(null);
    }
  }, [localRecommendationKeys, moveToNextRecordInCurrentTab, onDeleteRecommendation]);

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
    setExpandedThreadKeys((current) => new Set(current).add(key));
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

  const toggleActiveThread = useCallback(() => {
    if (!activeRecord) {
      return;
    }
    setExpandedThreadKeys((current) => {
      const next = new Set(current);
      if (next.has(activeRecord.key)) {
        next.delete(activeRecord.key);
      } else {
        next.add(activeRecord.key);
      }
      return next;
    });
  }, [activeRecord]);

  if (actionableRecommendations.length === 0 && !alwaysShow) return null;

  return (
    <div className="advice-shell recommendations">
      <header className="advice-hero">
        <div>
          <h2>Recommendations</h2>
          <p>Review portfolio advice, keep what you accept, discard the noise, and ask follow-up questions in context.</p>
        </div>
        <div className="advice-run-card" ref={analysisMenuRef}>
          <span>Last run</span>
          <strong>{latestAnalysisAt ? formatDateTime(latestAnalysisAt) : "Never"}</strong>
          <button
            type="button"
            onClick={() => setAnalysisPickerOpen((open) => !open)}
            title="Start a recommendation workflow"
            aria-expanded={analysisPickerOpen}
          >
            <Sparkles size={16} aria-hidden="true" />
            Analyze
          </button>
          {analysisPickerOpen && (
            <div className="advice-analysis-picker" role="menu" aria-label="Recommendation type">
              {WORKFLOW_ORDER.map((kind) => {
                const option = WORKFLOW_OPTIONS[kind];
                const Icon = option.icon;
                return (
                  <button
                    type="button"
                    role="menuitem"
                    key={kind}
                    onClick={() => {
                      void startWorkflowRecommendation(kind);
                    }}
                    disabled={startingWorkflow !== null}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span>
                      <strong>{option.label}</strong>
                      <small>{startingWorkflow === kind ? "Creating Codex request..." : option.description}</small>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </header>

      {shouldRerun && (
        <div className="recommendations-stale-alert advice-stale-alert" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <div>
            <strong>New portfolio data is available.</strong>
            <p>
              Analyze should be run again. Last run {latestAnalysisAt ? formatDateTime(latestAnalysisAt) : "never"}
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
                    <strong>{recommendationTitle(record.rec)}</strong>
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
                  : "Use Analyze to create your first working recommendation."}
              </p>
            </div>
          ) : (
            <>
              <div className="advice-pane-header">
                <div className="advice-title-block">
                  <div className="advice-title-row">
                    <div className="advice-title-main">
                      <h3>{recommendationTitle(activeRecord.rec)}</h3>
                      <span className="advice-category-tag">{categoryLabel(activeRecord.rec)}</span>
                    </div>
                    <StatusBadge status={activeRecord.status} severity={activeRecord.rec.severity} />
                  </div>
                </div>

                {activeSummary && <RecommendationSummaryCard summary={activeSummary} />}

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
                  {activeRecord.status === "discarded" && (
                    <button
                      type="button"
                      className="advice-action-button delete"
                      onClick={() => deleteDiscardedRecommendation(activeRecord)}
                      disabled={deletingKey === activeRecord.key}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                      {deletingKey === activeRecord.key ? "Deleting" : "Delete"}
                    </button>
                  )}
                </div>

                {activeError && (
                  <div className="advice-follow-up-error" role="alert">
                    {activeError}
                  </div>
                )}
              </div>

              <section className="advice-thread-panel">
                <button
                  type="button"
                  className="advice-thread-toggle"
                  onClick={toggleActiveThread}
                  aria-expanded={activeThreadExpanded}
                >
                  <MessageSquare size={16} aria-hidden="true" />
                  <span>
                    <strong>Chat & Codex prompt</strong>
                    <small>{activeThread.length} {activeThread.length === 1 ? "turn" : "turns"}</small>
                  </span>
                  {activeThreadExpanded ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
                </button>

                {activeThreadExpanded && (
                  <>
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
                            placeholder={`Ask about "${recommendationTitle(activeRecord.rec)}"...`}
                            aria-label={`Ask about ${recommendationTitle(activeRecord.rec)}`}
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
  const label = status === "working" ? "Working" : tabLabel(status);
  return (
    <span className={`advice-status-badge status-${status} severity-${severity}`}>
      <Icon size={12} aria-hidden="true" />
      {label}
    </span>
  );
}

function RecommendationSummaryCard({ summary }: { summary: RecommendationSummary }) {
  return (
    <div className={`advice-summary-card source-${summary.source}`}>
      <div className="advice-summary-main">
        <span className="advice-summary-icon" aria-hidden="true">
          <ListChecks size={17} />
        </span>
        <div>
          <p>{summary.headline}</p>
        </div>
      </div>

      {summary.bullets.length > 0 && (
        <ul className="advice-summary-bullets">
          {summary.bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
