import {
  AlertTriangle,
  Brain,
  DatabaseZap,
  Eye,
  EyeOff,
  LogOut,
  NotebookPen,
  RefreshCcw,
  Settings as SettingsIcon,
  Sparkles,
  Telescope,
  UserRound,
  WalletCards,
} from "lucide-react";
import { memo, startTransition, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  addManualCapitalEntry,
  askRecommendationFollowUp,
  fetchCommodityOpportunities,
  fetchCryptoOpportunities,
  fetchEtfOpportunities,
  fetchInvestorProfile,
  fetchManualCapital,
  fetchNotes,
  fetchOpenDataStock,
  fetchOpenDataStockAnalyses,
  fetchOpenDataStockAnalysis,
  fetchOpenDataStocks,
  fetchRecommendationFollowUpResult,
  fetchRecommendationFollowUps,
  fetchRefreshJobs,
  fetchRecommendations,
  fetchSnapshot,
  fetchUserConnections,
  fetchUserPreferences,
  generateRecommendations,
  refreshOpenDataStock,
  saveInvestorProfile as persistInvestorProfile,
  saveUserConnection,
  saveUserPreferences,
  startRefreshJob,
  createNote,
  updateNote,
  deleteNote,
  deleteManualCapitalEntry,
  deleteUserConnection,
  updateManualCapitalEntry,
  type BinanceLedgerEvent,
  type AssetOpportunity,
  type InvestorProfile,
  type ManualCapitalEntryRequest,
  type ManualCapitalSnapshot,
  type Note,
  type StockEntryAnalysis,
  type OpenDataStockSnapshot,
  type PortfolioSnapshot,
  type Recommendation,
  type RefreshJob,
  type RefreshSource,
  type SidebarView,
  type UserConnection,
  type UserConnectionSource,
  type UserConnectionUpdate,
} from "./api";
import { AssetInsightsTable } from "./components/AssetInsightsTable";
import { BinanceActivityTable } from "./components/BinanceActivityTable";
import { BreakdownTable } from "./components/BreakdownTable";
import { CashTable } from "./components/CashTable";
import { CapitalPanel } from "./components/CapitalPanel";
import { DataWarnings } from "./components/DataWarnings";
import { HoldingsTable } from "./components/HoldingsTable";
import { LandingLogin } from "./components/LandingLogin";
import { NotesPanel } from "./components/NotesPanel";
import {
  DEFAULT_CUSTOM_ALLOCATION,
  DEFAULT_INVESTOR_PERSONALITY,
  InvestorPersonalityPanel,
  normalizeInvestorPersonalityId,
  type InvestorAllocation,
  type InvestorAllocationKey,
  type InvestorPersonalityId,
} from "./components/InvestorPersonalityPanel";
import { OrdersTable } from "./components/OrdersTable";
import { OpenDataStockTable } from "./components/OpenDataStockTable";
import { Recommendations } from "./components/Recommendations";
import { SourceStatus, summarizeSourceStatuses } from "./components/SourceStatus";
import { SummaryCards } from "./components/SummaryCards";
import "./styles.css";

const STOCK_ASSET_CLASSES = new Set(["equity", "stock", "etf", "fund"]);
const STOCK_ANALYSIS_TAXONOMY_VERSION = "2026-06-05-v2";
const APP_SESSION_STORAGE_KEY = "invest-os:logged-in";
const INVESTOR_PERSONALITY_STORAGE_KEY = "invest-os:investor-personality";
const EMPTY_LEDGER_EVENTS: BinanceLedgerEvent[] = [];
const DEFAULT_SIDEBAR_ORDER: SidebarView[] = ["personality", "capital", "consultancy", "exploration", "eye", "notes"];
type AppView = "personality" | "capital" | "consultancy" | "exploration" | "eye" | "notes" | "settings";
type EyeAssetView = "stocks" | "crypto";

const SIDEBAR_ITEM_META = {
  personality: {
    icon: UserRound,
    label: "Personality",
    caption: "Profile",
  },
  capital: {
    icon: WalletCards,
    label: "Capital",
    caption: "Sources",
  },
  consultancy: {
    icon: Brain,
    label: "Consultancy",
    caption: "Advice",
  },
  exploration: {
    icon: Telescope,
    label: "Exploration",
    caption: "Research",
  },
  eye: {
    icon: Eye,
    label: "Eye",
    caption: "Portfolio",
  },
  notes: {
    icon: NotebookPen,
    label: "Notes",
    caption: "Markdown",
  },
} satisfies Record<SidebarView, { icon: typeof UserRound; label: string; caption: string }>;

type InvestorPersonalityState = {
  personality: InvestorPersonalityId;
  customAllocation: InvestorAllocation;
};

type FrozenPageProps = {
  active: boolean;
  className: string;
  children: ReactNode;
};

const FrozenPage = memo(
  function FrozenPage({ active, className, children }: FrozenPageProps) {
    const cachedChildrenRef = useRef<ReactNode>(children);
    if (active) {
      cachedChildrenRef.current = children;
    }

    return (
      <div className={className} hidden={!active}>
        {active ? children : cachedChildrenRef.current}
      </div>
    );
  },
  (previous, next) => !previous.active && !next.active && previous.className === next.className,
);

const INVESTOR_PERSONALITY_IDS = new Set<InvestorPersonalityId>([
  "capital_preservation",
  "steady_growth",
  "balanced_conviction",
  "aggressive_growth",
  "high_risk_explorer",
  "starter",
  "custom",
  "low_risk",
  "high_risk",
]);

const clampAllocationValue = (value: unknown, fallback: number) => {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return Math.min(100, Math.max(0, Math.round(numeric)));
};

const normalizeCustomAllocation = (allocation?: Partial<Record<InvestorAllocationKey, unknown>> | null) => {
  const source = allocation ?? {};
  return {
    vwce: clampAllocationValue(source.vwce, DEFAULT_CUSTOM_ALLOCATION.vwce),
    cashBonds: clampAllocationValue(source.cashBonds, DEFAULT_CUSTOM_ALLOCATION.cashBonds),
    individualStocks: clampAllocationValue(source.individualStocks, DEFAULT_CUSTOM_ALLOCATION.individualStocks),
    crypto: clampAllocationValue(source.crypto, DEFAULT_CUSTOM_ALLOCATION.crypto),
  };
};

const allocationTotal = (allocation: InvestorAllocation) =>
  Object.values(allocation).reduce((total, value) => total + value, 0);

const balanceCustomAllocation = (allocation: InvestorAllocation): InvestorAllocation => {
  const next = normalizeCustomAllocation(allocation);
  const delta = 100 - allocationTotal(next);

  if (delta === 0) {
    return next;
  }

  if (delta > 0) {
    return {
      ...next,
      cashBonds: clampAllocationValue(next.cashBonds + delta, next.cashBonds),
    };
  }

  let excess = Math.abs(delta);
  const reductionOrder: InvestorAllocationKey[] = ["cashBonds", "crypto", "individualStocks", "vwce"];
  reductionOrder.forEach((key) => {
    if (excess <= 0) {
      return;
    }
    const reduction = Math.min(next[key], excess);
    next[key] -= reduction;
    excess -= reduction;
  });
  return next;
};

const loadInvestorPersonality = (): InvestorPersonalityState => {
  if (typeof window === "undefined") {
    return {
      personality: DEFAULT_INVESTOR_PERSONALITY,
      customAllocation: DEFAULT_CUSTOM_ALLOCATION,
    };
  }
  try {
    const raw = window.localStorage.getItem(INVESTOR_PERSONALITY_STORAGE_KEY);
    if (!raw) {
      return {
        personality: DEFAULT_INVESTOR_PERSONALITY,
        customAllocation: DEFAULT_CUSTOM_ALLOCATION,
      };
    }
    const parsed = JSON.parse(raw) as Partial<InvestorPersonalityState>;
    return {
      personality:
        parsed.personality && INVESTOR_PERSONALITY_IDS.has(parsed.personality)
          ? normalizeInvestorPersonalityId(parsed.personality)
          : DEFAULT_INVESTOR_PERSONALITY,
      customAllocation: normalizeCustomAllocation(parsed.customAllocation),
    };
  } catch {
    return {
      personality: DEFAULT_INVESTOR_PERSONALITY,
      customAllocation: DEFAULT_CUSTOM_ALLOCATION,
    };
  }
};

const investorProfileToState = (profile: Pick<InvestorProfile, "personality" | "customAllocation">) => ({
  personality: INVESTOR_PERSONALITY_IDS.has(profile.personality)
    ? normalizeInvestorPersonalityId(profile.personality)
    : DEFAULT_INVESTOR_PERSONALITY,
  customAllocation: normalizeCustomAllocation(profile.customAllocation),
});

const cacheInvestorPersonality = (profile: InvestorPersonalityState) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(INVESTOR_PERSONALITY_STORAGE_KEY, JSON.stringify(profile));
  } catch {
    // Keep the dashboard usable if local storage is unavailable.
  }
};

const investorPersonalitiesEqual = (left: InvestorPersonalityState, right: InvestorPersonalityState) =>
  left.personality === right.personality &&
  left.customAllocation.vwce === right.customAllocation.vwce &&
  left.customAllocation.cashBonds === right.customAllocation.cashBonds &&
  left.customAllocation.individualStocks === right.customAllocation.individualStocks &&
  left.customAllocation.crypto === right.customAllocation.crypto;

const normalizeSidebarOrder = (order?: readonly string[] | null): SidebarView[] => {
  const allowed = new Set<SidebarView>(DEFAULT_SIDEBAR_ORDER);
  const seen = new Set<SidebarView>();
  const next: SidebarView[] = [];
  (order ?? []).forEach((item) => {
    if (allowed.has(item as SidebarView) && !seen.has(item as SidebarView)) {
      next.push(item as SidebarView);
      seen.add(item as SidebarView);
    }
  });
  DEFAULT_SIDEBAR_ORDER.forEach((item) => {
    if (!seen.has(item)) {
      next.push(item);
    }
  });
  return next;
};

const reorderSidebarOrder = (order: SidebarView[], from: SidebarView, to: SidebarView) => {
  const fromIndex = order.indexOf(from);
  const toIndex = order.indexOf(to);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) {
    return order;
  }
  const next = [...order];
  const [item] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, item);
  return next;
};

const isActiveRefreshJob = (job: RefreshJob) => job.status === "queued" || job.status === "running";

const addAmount = (values: Record<string, number>, key: string, amount: number) => {
  if (!Number.isFinite(amount) || Math.abs(amount) <= 0.00000001) {
    return;
  }
  const normalized = key.toUpperCase();
  values[normalized] = (values[normalized] ?? 0) + amount;
};

const latestSourceSyncTimestamp = (snapshot: PortfolioSnapshot | null) => {
  const timestamps = (snapshot?.source_sync_status ?? [])
    .map((status) => (status.last_synced_at ? new Date(status.last_synced_at).getTime() : Number.NaN))
    .filter(Number.isFinite);
  if (timestamps.length === 0) {
    return null;
  }
  return new Date(Math.max(...timestamps)).toISOString();
};

const loadAppSession = () => {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.localStorage.getItem(APP_SESSION_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
};

function DashboardApp({ onLogout }: { onLogout: () => void }) {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshSource, setRefreshSource] = useState<RefreshSource>("all");
  const [displayCurrency, setDisplayCurrency] = useState("EUR");
  const [activeView, setActiveView] = useState<AppView>("personality");
  const [visitedViews, setVisitedViews] = useState<Set<AppView>>(() => new Set(["personality"]));
  const [sidebarOrder, setSidebarOrder] = useState<SidebarView[]>(DEFAULT_SIDEBAR_ORDER);
  const [draggedSidebarView, setDraggedSidebarView] = useState<SidebarView | null>(null);
  const [eyePositionsView, setEyePositionsView] = useState<EyeAssetView>("stocks");
  const [eyeActivityView, setEyeActivityView] = useState<EyeAssetView>("stocks");
  const [eyePositionsCompact, setEyePositionsCompact] = useState(true);
  const [eyeOperationsCompact, setEyeOperationsCompact] = useState(true);
  const [eyeHideAbsoluteValues, setEyeHideAbsoluteValues] = useState(true);
  const [savedInvestorPersonality, setSavedInvestorPersonality] =
    useState<InvestorPersonalityState>(loadInvestorPersonality);
  const [investorPersonalityDraft, setInvestorPersonalityDraft] =
    useState<InvestorPersonalityState>(loadInvestorPersonality);
  const [investorProfileUpdatedAt, setInvestorProfileUpdatedAt] = useState<string | null>(null);
  const [investorProfileSaving, setInvestorProfileSaving] = useState(false);
  const [manualCapital, setManualCapital] = useState<ManualCapitalSnapshot | null>(null);
  const [manualCapitalSaving, setManualCapitalSaving] = useState(false);
  const [manualCapitalStatus, setManualCapitalStatus] = useState<string | null>(null);
  const [userConnections, setUserConnections] = useState<UserConnection[]>([]);
  const [connectionSaving, setConnectionSaving] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<string | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [noteTitleDraft, setNoteTitleDraft] = useState("");
  const [noteContentDraft, setNoteContentDraft] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteStatus, setNoteStatus] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recommendationsGeneratedAt, setRecommendationsGeneratedAt] = useState<string | null>(null);
  const [analyzingBrain, setAnalyzingBrain] = useState(false);
  const [openDataStocks, setOpenDataStocks] = useState<OpenDataStockSnapshot[]>([]);
  const [selectedOpenDataTicker, setSelectedOpenDataTicker] = useState("GOOGL");
  const [openDataStockLoading, setOpenDataStockLoading] = useState(false);
  const [openDataStockLoaded, setOpenDataStockLoaded] = useState(false);
  const [stockEntryAnalyses, setStockEntryAnalyses] = useState<Record<string, StockEntryAnalysis>>({});
  const [stockEntryAnalysesLoading, setStockEntryAnalysesLoading] = useState(false);
  const [stockEntryAnalysesLoadedKey, setStockEntryAnalysesLoadedKey] = useState("");
  const [etfInsights, setEtfInsights] = useState<AssetOpportunity[]>([]);
  const [cryptoInsights, setCryptoInsights] = useState<AssetOpportunity[]>([]);
  const [commodityInsights, setCommodityInsights] = useState<AssetOpportunity[]>([]);
  const [assetInsightsLoading, setAssetInsightsLoading] = useState(false);
  const [assetInsightsLoaded, setAssetInsightsLoaded] = useState(false);
  const [refreshJobs, setRefreshJobs] = useState<RefreshJob[]>([]);
  const [refreshStartPending, setRefreshStartPending] = useState(false);
  const refreshJobsRef = useRef<RefreshJob[]>([]);

  const loadPortfolioData = useCallback(async () => {
    const [snap, recommendationSnapshot] = await Promise.all([fetchSnapshot(), fetchRecommendations()]);
    startTransition(() => {
      setSnapshot(snap);
      setRecommendations(recommendationSnapshot.recommendations);
      setRecommendationsGeneratedAt(recommendationSnapshot.generated_at ?? null);
    });
  }, []);

  const pollRefreshJobs = useCallback(async (isCancelled?: () => boolean) => {
    try {
      const jobs = await fetchRefreshJobs();
      if (isCancelled?.()) {
        return;
      }
      const previousById = new Map(refreshJobsRef.current.map((job) => [job.id, job]));
      const finishedSinceLastPoll = jobs.some((job) => {
        const previous = previousById.get(job.id);
        return previous && isActiveRefreshJob(previous) && !isActiveRefreshJob(job);
      });
      const successfulCompletion = jobs.some((job) => {
        const previous = previousById.get(job.id);
        return previous && isActiveRefreshJob(previous) && job.status === "success";
      });
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      if (successfulCompletion) {
        await loadPortfolioData();
      }
      if (finishedSinceLastPoll) {
        setLoading(false);
      }
    } catch {
      // Keep the dashboard usable if the transient polling endpoint misses once.
    }
  }, [loadPortfolioData]);

  const showView = useCallback((view: AppView) => {
    setVisitedViews((current) => {
      if (current.has(view)) {
        return current;
      }
      const next = new Set(current);
      next.add(view);
      return next;
    });
    setActiveView(view);
  }, []);
  const persistSidebarOrder = useCallback((order: SidebarView[]) => {
    saveUserPreferences({ sidebar_order: order }).catch((err) => {
      setError(err instanceof Error ? err.message : "Could not save sidebar order.");
    });
  }, []);
  const dropSidebarView = useCallback((target: SidebarView) => {
    setDraggedSidebarView((dragged) => {
      if (!dragged) {
        return null;
      }
      setSidebarOrder((current) => {
        const next = reorderSidebarOrder(current, dragged, target);
        if (next !== current) {
          persistSidebarOrder(next);
        }
        return next;
      });
      return null;
    });
  }, [persistSidebarOrder]);
  const explorationVisited = visitedViews.has("exploration");

  const selectInvestorPersonality = useCallback((personality: InvestorPersonalityId) => {
    setInvestorPersonalityDraft((current) => ({ ...current, personality }));
  }, []);

  const updateCustomAllocation = useCallback((key: InvestorAllocationKey, value: number) => {
    setInvestorPersonalityDraft((current) => ({
      personality: "custom",
      customAllocation: {
        ...current.customAllocation,
        [key]: clampAllocationValue(value, current.customAllocation[key]),
      },
    }));
  }, []);

  const rebalanceCustomAllocation = useCallback(() => {
    setInvestorPersonalityDraft((current) => ({
      personality: "custom",
      customAllocation: balanceCustomAllocation(current.customAllocation),
    }));
  }, []);

  const investorProfileDirty = useMemo(
    () => !investorPersonalitiesEqual(savedInvestorPersonality, investorPersonalityDraft),
    [investorPersonalityDraft, savedInvestorPersonality],
  );
  const investorProfileCanSave = useMemo(
    () =>
      investorPersonalityDraft.personality !== "custom" ||
      allocationTotal(investorPersonalityDraft.customAllocation) === 100,
    [investorPersonalityDraft],
  );

  const saveInvestorPersonality = useCallback(async () => {
    if (!investorProfileCanSave || !investorProfileDirty) {
      return;
    }
    setInvestorProfileSaving(true);
    setError(null);
    try {
      const saved = await persistInvestorProfile({
        personality: investorPersonalityDraft.personality,
        customAllocation: investorPersonalityDraft.customAllocation,
      });
      const next = investorProfileToState(saved);
      setSavedInvestorPersonality(next);
      setInvestorPersonalityDraft(next);
      setInvestorProfileUpdatedAt(saved.updated_at ?? null);
      cacheInvestorPersonality(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save investor personality.");
    } finally {
      setInvestorProfileSaving(false);
    }
  }, [investorPersonalityDraft, investorProfileCanSave, investorProfileDirty]);

  const saveManualCapitalEntry = useCallback(async (entry: ManualCapitalEntryRequest) => {
    setManualCapitalSaving(true);
    setManualCapitalStatus(null);
    setError(null);
    try {
      const updated = await addManualCapitalEntry(entry);
      setManualCapital(updated);
      const job = await startRefreshJob("manual");
      const jobs = await fetchRefreshJobs().catch(() => [job]);
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      setManualCapitalStatus("Saved. Manual refresh started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save manual capital entry.");
    } finally {
      setManualCapitalSaving(false);
    }
  }, []);

  const updateCapitalEntry = useCallback(async (entryId: string, entry: ManualCapitalEntryRequest) => {
    setManualCapitalSaving(true);
    setManualCapitalStatus(null);
    setError(null);
    try {
      const updated = await updateManualCapitalEntry(entryId, entry);
      setManualCapital(updated);
      const job = await startRefreshJob("manual");
      const jobs = await fetchRefreshJobs().catch(() => [job]);
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      setManualCapitalStatus("Updated. Manual refresh started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update capital entry.");
    } finally {
      setManualCapitalSaving(false);
    }
  }, []);

  const deleteCapitalEntry = useCallback(async (entryId: string, label: string) => {
    if (!window.confirm(`Delete ${label}?`)) {
      return;
    }
    setManualCapitalSaving(true);
    setManualCapitalStatus(null);
    setError(null);
    try {
      const updated = await deleteManualCapitalEntry(entryId);
      setManualCapital(updated);
      const job = await startRefreshJob("manual");
      const jobs = await fetchRefreshJobs().catch(() => [job]);
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      setManualCapitalStatus("Deleted. Manual refresh started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete capital entry.");
    } finally {
      setManualCapitalSaving(false);
    }
  }, []);

  const configureCapitalConnection = useCallback((source: "ibkr" | "binance") => {
    setRefreshSource(source);
    showView("settings");
  }, [showView]);

  const saveCapitalConnection = useCallback(async (source: UserConnectionSource, connection: UserConnectionUpdate) => {
    setConnectionSaving(true);
    setConnectionStatus(null);
    setError(null);
    try {
      const saved = await saveUserConnection(source, connection);
      setUserConnections((current) => {
        const without = current.filter((item) => item.source !== saved.source);
        return [...without, saved].sort((left, right) => left.source.localeCompare(right.source));
      });
      setConnectionStatus(`${saved.label} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save connection.");
    } finally {
      setConnectionSaving(false);
    }
  }, []);

  const deleteCapitalConnection = useCallback(async (source: UserConnectionSource, label: string) => {
    if (!window.confirm(`Delete ${label}? This disconnects the source and removes its cached capital from the app.`)) {
      return;
    }
    setConnectionSaving(true);
    setConnectionStatus(null);
    setError(null);
    try {
      const deleted = await deleteUserConnection(source);
      setUserConnections((current) => {
        const without = current.filter((item) => item.source !== deleted.source);
        return [...without, deleted].sort((left, right) => left.source.localeCompare(right.source));
      });
      await loadPortfolioData();
      setConnectionStatus(`${deleted.label} deleted.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete connection.");
    } finally {
      setConnectionSaving(false);
    }
  }, [loadPortfolioData]);

  const refreshCapitalConnection = useCallback(async (source: UserConnectionSource) => {
    setConnectionStatus(null);
    setError(null);
    try {
      const job = await startRefreshJob(source);
      const jobs = await fetchRefreshJobs().catch(() => [job]);
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      setRefreshSource(source);
      setConnectionStatus(`${source === "ibkr" ? "IBKR" : "Binance"} refresh started.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh connection.");
    }
  }, []);

  const selectedNote = useMemo(
    () => notes.find((note) => note.id === selectedNoteId) ?? null,
    [notes, selectedNoteId],
  );
  const noteDirty = useMemo(() => {
    if (!selectedNote) {
      return noteTitleDraft.trim() !== "" || noteContentDraft.trim() !== "";
    }
    return selectedNote.title !== noteTitleDraft || selectedNote.content !== noteContentDraft;
  }, [noteContentDraft, noteTitleDraft, selectedNote]);

  const selectNote = useCallback((note: Note) => {
    if (noteDirty && !window.confirm("Discard unsaved note changes?")) {
      return;
    }
    setSelectedNoteId(note.id);
    setNoteTitleDraft(note.title);
    setNoteContentDraft(note.content);
    setNoteStatus(null);
  }, [noteDirty]);

  const newNote = useCallback(() => {
    if (noteDirty && !window.confirm("Discard unsaved note changes?")) {
      return;
    }
    setSelectedNoteId(null);
    setNoteTitleDraft("");
    setNoteContentDraft("");
    setNoteStatus(null);
  }, [noteDirty]);

  const saveNote = useCallback(async () => {
    if (!noteDirty) {
      return;
    }
    setNoteSaving(true);
    setNoteStatus(null);
    setError(null);
    try {
      const payload = {
        title: noteTitleDraft.trim() || "Untitled note",
        content: noteContentDraft,
      };
      const saved = selectedNoteId
        ? await updateNote(selectedNoteId, payload)
        : await createNote(payload);
      setNotes((current) => {
        const withoutSaved = current.filter((note) => note.id !== saved.id);
        return [saved, ...withoutSaved].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
      });
      setSelectedNoteId(saved.id);
      setNoteTitleDraft(saved.title);
      setNoteContentDraft(saved.content);
      setNoteStatus("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save note.");
    } finally {
      setNoteSaving(false);
    }
  }, [noteContentDraft, noteDirty, noteTitleDraft, selectedNoteId]);

  const removeNote = useCallback(async () => {
    if (!selectedNoteId) {
      return;
    }
    if (!window.confirm("Delete this note?")) {
      return;
    }
    setNoteSaving(true);
    setError(null);
    try {
      await deleteNote(selectedNoteId);
      setNotes((current) => {
        const next = current.filter((note) => note.id !== selectedNoteId);
        const first = next[0] ?? null;
        setSelectedNoteId(first?.id ?? null);
        setNoteTitleDraft(first?.title ?? "");
        setNoteContentDraft(first?.content ?? "");
        return next;
      });
      setNoteStatus("Deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete note.");
    } finally {
      setNoteSaving(false);
    }
  }, [selectedNoteId]);

  const hasActiveRefreshJob = useMemo(() => refreshJobs.some(isActiveRefreshJob), [refreshJobs]);

  useEffect(() => {
    let cancelled = false;
    fetchInvestorProfile()
      .then((profile) => {
        if (cancelled) {
          return;
        }
        const next = investorProfileToState(profile);
        setSavedInvestorPersonality(next);
        setInvestorProfileUpdatedAt(profile.updated_at ?? null);
        if (profile.updated_at) {
          setInvestorPersonalityDraft(next);
          cacheInvestorPersonality(next);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load investor personality.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchManualCapital()
      .then((capital) => {
        if (!cancelled) {
          setManualCapital(capital);
        }
      })
      .catch(() => {
        // Manual files are optional during first setup.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchUserConnections()
      .then((connections) => {
        if (!cancelled) {
          setUserConnections(connections);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load connections.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchUserPreferences()
      .then((preferences) => {
        if (!cancelled) {
          setSidebarOrder(normalizeSidebarOrder(preferences.sidebar_order));
        }
      })
      .catch(() => {
        // Sidebar order is optional; keep the default if preferences cannot load.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchNotes()
      .then((savedNotes) => {
        if (cancelled) {
          return;
        }
        setNotes(savedNotes);
        const first = savedNotes[0] ?? null;
        setSelectedNoteId(first?.id ?? null);
        setNoteTitleDraft(first?.title ?? "");
        setNoteContentDraft(first?.content ?? "");
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load notes.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadPortfolioData()
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load snapshot."))
      .finally(() => setLoading(false));
    pollRefreshJobs(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [loadPortfolioData, pollRefreshJobs]);

  useEffect(() => {
    if (!hasActiveRefreshJob) {
      return;
    }
    let cancelled = false;
    const interval = window.setInterval(() => pollRefreshJobs(() => cancelled), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [hasActiveRefreshJob, pollRefreshJobs]);

  useEffect(() => {
    if (!explorationVisited || openDataStocks.length > 0 || openDataStockLoading || openDataStockLoaded) {
      return;
    }
    setOpenDataStockLoading(true);
    fetchOpenDataStocks()
      .then(async (snapshots) => {
        if (snapshots.length > 0) {
          setOpenDataStocks(snapshots);
          setSelectedOpenDataTicker((ticker) =>
            snapshots.some((snapshot) => snapshot.ticker === ticker) ? ticker : snapshots[0].ticker,
          );
          return;
        }
        const snapshot = await fetchOpenDataStock("GOOGL");
        setOpenDataStocks([snapshot]);
        setSelectedOpenDataTicker(snapshot.ticker);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load open-data stocks."))
      .finally(() => {
        setOpenDataStockLoaded(true);
        setOpenDataStockLoading(false);
      });
  }, [explorationVisited, openDataStocks.length, openDataStockLoaded, openDataStockLoading]);

  useEffect(() => {
    if (!explorationVisited || assetInsightsLoading || assetInsightsLoaded) {
      return;
    }
    setAssetInsightsLoading(true);
    Promise.all([fetchEtfOpportunities(), fetchCryptoOpportunities(), fetchCommodityOpportunities()])
      .then(([etfs, crypto, commodities]) => {
        setEtfInsights(etfs);
        setCryptoInsights(crypto);
        setCommodityInsights(commodities);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load asset insights."))
      .finally(() => {
        setAssetInsightsLoaded(true);
        setAssetInsightsLoading(false);
      });
  }, [assetInsightsLoaded, assetInsightsLoading, explorationVisited]);

  useEffect(() => {
    if (!explorationVisited || openDataStocks.length === 0 || stockEntryAnalysesLoading) {
      return;
    }
    const analysisKey = `${STOCK_ANALYSIS_TAXONOMY_VERSION}:${openDataStocks
      .map((snapshot) => `${snapshot.ticker}:${snapshot.generated_at}`)
      .join("|")}`;
    if (stockEntryAnalysesLoadedKey === analysisKey) {
      return;
    }
    setStockEntryAnalysesLoading(true);
    fetchOpenDataStockAnalyses()
      .then((analyses) => {
        setStockEntryAnalyses(analyses);
        setStockEntryAnalysesLoadedKey(analysisKey);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load stock analyses."))
      .finally(() => {
        setStockEntryAnalysesLoading(false);
      });
  }, [
    openDataStocks,
    explorationVisited,
    stockEntryAnalysesLoadedKey,
    stockEntryAnalysesLoading,
  ]);

  const refresh = useCallback(async () => {
    setRefreshStartPending(true);
    setError(null);
    try {
      const job = await startRefreshJob(refreshSource);
      const jobs = await fetchRefreshJobs().catch(() => [job]);
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      if (jobs.some((item) => item.id === job.id && item.status === "success")) {
        await loadPortfolioData();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh snapshot.");
    } finally {
      setRefreshStartPending(false);
    }
  }, [loadPortfolioData, refreshSource]);

  const analyzeBrain = useCallback(async () => {
    setAnalyzingBrain(true);
    setError(null);
    try {
      const recommendationSnapshot = await generateRecommendations();
      setRecommendations(recommendationSnapshot.recommendations);
      setRecommendationsGeneratedAt(recommendationSnapshot.generated_at ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run consultancy analysis.");
    } finally {
      setAnalyzingBrain(false);
    }
  }, []);

  const collectOpenDataStockFacts = useCallback(async (ticker: string) => {
    setOpenDataStockLoading(true);
    setStockEntryAnalysesLoading(true);
    setError(null);
    try {
      const snapshot = await refreshOpenDataStock(ticker);
      const analysis = await fetchOpenDataStockAnalysis(ticker);
      setOpenDataStocks((snapshots) => {
        const next = snapshots.filter((item) => item.ticker !== snapshot.ticker);
        next.push(snapshot);
        next.sort((left, right) => left.ticker.localeCompare(right.ticker));
        return next;
      });
      setSelectedOpenDataTicker(snapshot.ticker);
      setStockEntryAnalyses((analyses) => (analysis ? { ...analyses, [snapshot.ticker]: analysis } : analyses));
      setStockEntryAnalysesLoadedKey("");
      setOpenDataStockLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not collect ${ticker} facts.`);
    } finally {
      setOpenDataStockLoading(false);
      setStockEntryAnalysesLoading(false);
    }
  }, []);

  const displayRate = useMemo(
    () => snapshot?.display_rates.find((rate) => rate.currency === displayCurrency)?.rate_from_base ?? 1,
    [displayCurrency, snapshot?.display_rates],
  );
  const canShowUsd = useMemo(
    () => Boolean(snapshot?.display_rates.some((rate) => rate.currency === "USD")),
    [snapshot?.display_rates],
  );

  const cryptoHoldings = useMemo(
    () =>
      (snapshot?.holdings ?? []).filter(
        (holding) => holding.source === "binance" || holding.asset_class.toLowerCase() === "crypto",
      ),
    [snapshot?.holdings],
  );
  const cryptoOpenOrders = useMemo(
    () => (snapshot?.open_orders ?? []).filter((order) => order.source === "binance"),
    [snapshot?.open_orders],
  );
  const cryptoCashBalances = useMemo(
    () =>
      (snapshot?.cash_balances ?? []).filter(
        (cash) => cash.source === "binance" && cash.currency.toUpperCase() === "USDC",
      ),
    [snapshot?.cash_balances],
  );
  const cryptoOrderHistory = useMemo(
    () => (snapshot?.order_history ?? []).filter((order) => order.source === "binance"),
    [snapshot?.order_history],
  );
  const cryptoLedgerEvents = useMemo(
    () => (snapshot?.ledger_events ?? []).filter((event) => event.source === "binance"),
    [snapshot?.ledger_events],
  );
  const stockHoldings = useMemo(
    () =>
      (snapshot?.holdings ?? []).filter(
        (holding) =>
          holding.asset_class.toLowerCase() !== "rsu" &&
          (holding.source === "ibkr" || STOCK_ASSET_CLASSES.has(holding.asset_class.toLowerCase())),
      ),
    [snapshot?.holdings],
  );
  const stockOpenOrders = useMemo(
    () => (snapshot?.open_orders ?? []).filter((order) => order.source === "ibkr"),
    [snapshot?.open_orders],
  );
  const stockCashBalances = useMemo(
    () => (snapshot?.cash_balances ?? []).filter((cash) => cash.source === "ibkr"),
    [snapshot?.cash_balances],
  );
  const stockOrderHistory = useMemo(
    () => (snapshot?.order_history ?? []).filter((order) => order.source === "ibkr"),
    [snapshot?.order_history],
  );
  const usdDisplayRate = useMemo(
    () => snapshot?.display_rates.find((rate) => rate.currency === "USD")?.rate_from_base ?? 1,
    [snapshot?.display_rates],
  );
  const currentCryptoBalances = useMemo(() => {
    const values: Record<string, number> = {};
    cryptoHoldings
      .filter((holding) => holding.source === "binance")
      .forEach((holding) => {
        addAmount(values, holding.symbol, holding.quantity);
      });
    (snapshot?.cash_balances ?? [])
      .filter((cash) => cash.source === "binance")
      .forEach((cash) => {
        addAmount(values, cash.currency, cash.balance);
      });
    return values;
  }, [cryptoHoldings, snapshot?.cash_balances]);
  const currentCryptoAssetValues = useMemo(() => {
    const values: Record<string, number> = {};
    cryptoHoldings
      .filter((holding) => holding.source === "binance")
      .forEach((holding) => {
        if (holding.value_in_base != null) {
          addAmount(values, holding.symbol, holding.value_in_base * usdDisplayRate);
        }
      });
    (snapshot?.cash_balances ?? [])
      .filter((cash) => cash.source === "binance")
      .forEach((cash) => {
        if (cash.value_in_base != null) {
          addAmount(values, cash.currency, cash.value_in_base * usdDisplayRate);
        }
    });
    return values;
  }, [cryptoHoldings, snapshot?.cash_balances, usdDisplayRate]);
  const consultancyRecommendations = recommendations;
  const activeEyePositionLabel = eyePositionsView === "stocks" ? "Stocks" : "Crypto";
  const activeEyeHoldings = eyePositionsView === "stocks" ? stockHoldings : cryptoHoldings;
  const activeEyeOpenOrders = eyePositionsView === "stocks" ? stockOpenOrders : cryptoOpenOrders;
  const activeEyeCashBalances = eyePositionsView === "stocks" ? stockCashBalances : cryptoCashBalances;
  const activeEyeActivityOrders = eyeActivityView === "stocks" ? stockOrderHistory : cryptoOrderHistory;
  const activeEyeActivityEvents = eyeActivityView === "stocks" ? EMPTY_LEDGER_EVENTS : cryptoLedgerEvents;
  const activeEyeActivityEmptyLabel =
    eyeActivityView === "stocks"
      ? "No IBKR executions cached yet. Refresh IBKR to import Flex history; if it stays empty, check that the Flex query includes Trades and IBKR can generate the statement."
      : "No crypto activity loaded.";
  const activeRefreshJobs = useMemo(() => refreshJobs.filter(isActiveRefreshJob), [refreshJobs]);
  const sourceSyncStatuses = useMemo(
    () => summarizeSourceStatuses(snapshot?.source_sync_status ?? []),
    [snapshot?.source_sync_status],
  );
  const latestSourceSyncedAt = useMemo(() => latestSourceSyncTimestamp(snapshot), [snapshot]);
  const warningCount = snapshot?.data_warnings.length ?? 0;
  const syncIssueCount = useMemo(
    () => sourceSyncStatuses.filter((status) => status.status !== "success").length ?? 0,
    [sourceSyncStatuses],
  );
  const hasIbkrFlex1001Warning = useMemo(
    () =>
      (snapshot?.source_sync_status ?? []).some(
        (status) =>
          status.source === "ibkr_history" &&
          status.warning?.toLowerCase().includes("1001"),
      ),
    [snapshot?.source_sync_status],
  );
  const pageMeta = {
    personality: {
      title: "Personality",
      subtitle: "Risk profile and target allocation.",
    },
    capital: {
      title: "Capital",
      subtitle: "Manual entries, connected accounts, and file imports.",
    },
    consultancy: {
      title: "Consultancy",
      subtitle: "Ask Brain, review recommendations, and compare AI entry candidates.",
    },
    exploration: {
      title: "Exploration",
      subtitle: "Stock insights, ETFs, crypto, and commodities.",
    },
    eye: {
      title: "Eye",
      subtitle: "Portfolio value, platform breakdown, positions, orders, cash, and activity.",
    },
    notes: {
      title: "Notes",
      subtitle: "Markdown notes, decisions, and review reminders.",
    },
    settings: {
      title: "Settings",
      subtitle: "Refresh, source sync, warnings, and display preferences.",
    },
  } satisfies Record<AppView, { title: string; subtitle: string }>;
  const settingsNotificationCount = activeRefreshJobs.length + syncIssueCount + warningCount;
  const showPageHeader = activeView !== "capital" && activeView !== "personality" && activeView !== "consultancy";

  return (
    <div className="invest-app">
      <aside className="invest-sidebar" aria-label="Invest OS navigation">
        <div className="invest-brand">
          <div className="invest-brand-mark">
            <Sparkles size={18} aria-hidden="true" />
          </div>
          <div>
            <strong>Invest OS</strong>
            <span>AI investing</span>
          </div>
        </div>

        <nav className="invest-nav">
          {sidebarOrder.map((view) => {
            const meta = SIDEBAR_ITEM_META[view];
            const Icon = meta.icon;
            const isActive = activeView === view;
            return (
              <div
                className={`invest-nav-item ${draggedSidebarView === view ? "dragging" : ""}`}
                key={view}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  dropSidebarView(view);
                }}
              >
                <button
                  type="button"
                  className={`invest-nav-main ${isActive ? "active" : ""}`}
                  draggable
                  onClick={() => showView(view)}
                  onDragStart={(event) => {
                    setDraggedSidebarView(view);
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", view);
                  }}
                  onDragEnd={() => setDraggedSidebarView(null)}
                  title="Drag to reorder"
                >
                  <Icon size={18} aria-hidden="true" />
                  <span>{meta.label}</span>
                  <small>{meta.caption}</small>
                </button>
              </div>
            );
          })}
        </nav>

        <nav className="invest-nav invest-settings-nav">
          <button
            type="button"
            className={`invest-nav-main ${activeView === "settings" ? "active" : ""}`}
            onClick={() => showView("settings")}
          >
            <SettingsIcon size={18} aria-hidden="true" />
            <span>Settings</span>
            {settingsNotificationCount > 0 && <small>{settingsNotificationCount}</small>}
          </button>
          <button type="button" className="invest-nav-main invest-logout-button" onClick={onLogout}>
            <LogOut size={18} aria-hidden="true" />
            <span>Logout</span>
            <small>ignig22</small>
          </button>
        </nav>
      </aside>

      <main className="invest-main">
        {showPageHeader && (
          <header className="topbar invest-page-header">
            <div>
              <p>Investment Operating System</p>
              <h1>{pageMeta[activeView].title}</h1>
              <span>{pageMeta[activeView].subtitle}</span>
            </div>
          </header>
        )}

        {error && <section className="error">{error}</section>}
        {!snapshot && !error && <section className="loading">Loading portfolio snapshot...</section>}

        {visitedViews.has("personality") && (
          <FrozenPage className="app-page personality-page" active={activeView === "personality"}>
            <InvestorPersonalityPanel
              personality={investorPersonalityDraft.personality}
              customAllocation={investorPersonalityDraft.customAllocation}
              onPersonalityChange={selectInvestorPersonality}
              onCustomAllocationChange={updateCustomAllocation}
              onCustomAllocationBalance={rebalanceCustomAllocation}
              onSave={saveInvestorPersonality}
              dirty={investorProfileDirty}
              saving={investorProfileSaving}
              canSave={investorProfileCanSave}
              savedAt={investorProfileUpdatedAt}
            />
          </FrozenPage>
        )}

        {visitedViews.has("capital") && (
          <FrozenPage className="app-page capital-page" active={activeView === "capital"}>
            <CapitalPanel
              manualCapital={manualCapital}
              snapshot={snapshot}
              connections={userConnections}
              saving={manualCapitalSaving}
              status={manualCapitalStatus}
              connectionSaving={connectionSaving}
              connectionStatus={connectionStatus}
              onSaveManualEntry={saveManualCapitalEntry}
              onUpdateManualEntry={updateCapitalEntry}
              onDeleteManualEntry={deleteCapitalEntry}
              onConfigureConnection={configureCapitalConnection}
              onSaveConnection={saveCapitalConnection}
              onDeleteConnection={deleteCapitalConnection}
              onRefreshConnection={refreshCapitalConnection}
            />
          </FrozenPage>
        )}

        {snapshot && visitedViews.has("consultancy") && (
          <FrozenPage className="app-page consultancy-page" active={activeView === "consultancy"}>
            <Recommendations
              recommendations={consultancyRecommendations}
              generatedAt={recommendationsGeneratedAt}
              latestSourceSyncedAt={latestSourceSyncedAt}
              analyzing={analyzingBrain}
              onAnalyze={analyzeBrain}
              onAskRecommendation={askRecommendationFollowUp}
              onLoadRecommendationFollowUps={fetchRecommendationFollowUps}
              onPollRecommendation={fetchRecommendationFollowUpResult}
              alwaysShow
            />
          </FrozenPage>
        )}

        {snapshot && visitedViews.has("exploration") && (
          <FrozenPage className="app-page exploration-page" active={activeView === "exploration"}>
            <section className="positions-section exploration-insights">
              <OpenDataStockTable
                snapshots={openDataStocks}
                selectedTicker={selectedOpenDataTicker}
                loading={openDataStockLoading}
                analyses={stockEntryAnalyses}
                analysisLoading={stockEntryAnalysesLoading}
                onSelectTicker={setSelectedOpenDataTicker}
                onRefresh={collectOpenDataStockFacts}
              />
              <AssetInsightsTable
                title="ETF Insights"
                assets={etfInsights}
                loading={assetInsightsLoading}
                kind="etf"
                emptyLabel="No ETF deterministic metrics loaded. Run python scripts/build_asset_derived_signals.py."
              />
              <AssetInsightsTable
                title="Crypto Insights"
                assets={cryptoInsights}
                loading={assetInsightsLoading}
                kind="crypto"
                emptyLabel="No crypto deterministic metrics loaded. Run python scripts/build_asset_derived_signals.py."
              />
              <AssetInsightsTable
                title="Commodities Insights"
                assets={commodityInsights}
                loading={assetInsightsLoading}
                kind="commodity_proxy"
                emptyLabel="No commodity-proxy deterministic metrics loaded. Run python scripts/build_asset_derived_signals.py."
              />
            </section>
          </FrozenPage>
        )}

        {snapshot && visitedViews.has("eye") && (
          <FrozenPage className="app-page eye-page" active={activeView === "eye"}>
            <div className="connector-body">
              <section className="eye-privacy-toolbar" aria-label="Eye privacy controls">
                <div>
                  <strong>{eyeHideAbsoluteValues ? "Relative view" : "Full values"}</strong>
                  <span>
                    {eyeHideAbsoluteValues
                      ? "Absolute money values are hidden. Percentages, counts, bars, ROI, and quantities stay visible."
                      : "Show absolute money values across Eye."}
                  </span>
                </div>
                <button
                  type="button"
                  className={`eye-privacy-toggle ${eyeHideAbsoluteValues ? "active" : ""}`}
                  onClick={() => setEyeHideAbsoluteValues((current) => !current)}
                  aria-pressed={eyeHideAbsoluteValues}
                  title={eyeHideAbsoluteValues ? "Show absolute money values" : "Hide absolute money values"}
                >
                  {eyeHideAbsoluteValues ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                  {eyeHideAbsoluteValues ? "Show totals" : "Hide totals"}
                </button>
              </section>

              <SummaryCards
                snapshot={snapshot}
                displayCurrency={displayCurrency}
                displayRate={displayRate}
                hideAbsoluteValues={eyeHideAbsoluteValues}
              />

              <BreakdownTable
                title="Platform Breakdown"
                items={snapshot.platform_breakdown}
                currency={displayCurrency}
                displayRate={displayRate}
                hideAbsoluteValues={eyeHideAbsoluteValues}
                holdings={snapshot.holdings}
                cashBalances={snapshot.cash_balances}
                openOrders={snapshot.open_orders}
                displayRates={snapshot.display_rates}
              />

              <section className="positions-section eye-tables">
                <HoldingsTable
                  title="Positions"
                  holdings={activeEyeHoldings}
                  displayCurrency={displayCurrency}
                  displayRate={displayRate}
                  compact={eyePositionsCompact}
                  hideAbsoluteValues={eyeHideAbsoluteValues}
                  controls={
                    <div className="eye-panel-controls">
                      <div className="segmented segmented-compact" aria-label="Position asset type">
                        <button
                          type="button"
                          className={eyePositionsView === "stocks" ? "active" : ""}
                          onClick={() => setEyePositionsView("stocks")}
                        >
                          Stocks
                        </button>
                        <button
                          type="button"
                          className={eyePositionsView === "crypto" ? "active" : ""}
                          onClick={() => setEyePositionsView("crypto")}
                        >
                          Crypto
                        </button>
                      </div>
                      <button
                        type="button"
                        className="table-view-toggle"
                        onClick={() => setEyePositionsCompact((current) => !current)}
                      >
                        {eyePositionsCompact ? "Full table" : "Simple view"}
                      </button>
                    </div>
                  }
                />
                <BinanceActivityTable
                  key={eyeActivityView}
                  title="Operations"
                  orders={activeEyeActivityOrders}
                  events={activeEyeActivityEvents}
                  emptyLabel={activeEyeActivityEmptyLabel}
                  compact={eyeOperationsCompact}
                  endTimestamp={eyeActivityView === "crypto" ? snapshot.generated_at : undefined}
                  currentBalances={eyeActivityView === "crypto" ? currentCryptoBalances : undefined}
                  currentAssetValues={eyeActivityView === "crypto" ? currentCryptoAssetValues : undefined}
                  hideAbsoluteValues={eyeHideAbsoluteValues}
                  controls={
                    <div className="eye-panel-controls">
                      <div className="segmented segmented-compact" aria-label="Operations asset type">
                        <button
                          type="button"
                          className={eyeActivityView === "stocks" ? "active" : ""}
                          onClick={() => setEyeActivityView("stocks")}
                        >
                          Stocks
                        </button>
                        <button
                          type="button"
                          className={eyeActivityView === "crypto" ? "active" : ""}
                          onClick={() => setEyeActivityView("crypto")}
                        >
                          Crypto
                        </button>
                      </div>
                      <button
                        type="button"
                        className="table-view-toggle"
                        onClick={() => setEyeOperationsCompact((current) => !current)}
                      >
                        {eyeOperationsCompact ? "Full table" : "Simple view"}
                      </button>
                    </div>
                  }
                />
                <OrdersTable
                  title={`${activeEyePositionLabel} Open Orders`}
                  orders={activeEyeOpenOrders}
                  cashBalances={activeEyeCashBalances}
                  hideAbsoluteValues={eyeHideAbsoluteValues}
                />
                <CashTable
                  cash={activeEyeCashBalances}
                  displayCurrency={displayCurrency}
                  displayRate={displayRate}
                  hideAbsoluteValues={eyeHideAbsoluteValues}
                />
              </section>
            </div>
          </FrozenPage>
        )}

        {visitedViews.has("notes") && (
          <FrozenPage className="app-page notes-page" active={activeView === "notes"}>
            <NotesPanel
              notes={notes}
              selectedNoteId={selectedNoteId}
              title={noteTitleDraft}
              content={noteContentDraft}
              dirty={noteDirty}
              saving={noteSaving}
              status={noteStatus}
              onSelectNote={selectNote}
              onNewNote={newNote}
              onTitleChange={setNoteTitleDraft}
              onContentChange={setNoteContentDraft}
              onSave={saveNote}
              onDelete={removeNote}
            />
          </FrozenPage>
        )}

        {snapshot && visitedViews.has("settings") && (
          <FrozenPage className="app-page settings-page" active={activeView === "settings"}>
            <section className="panel settings-panel">
              <div className="panel-heading">
                <h2>Refresh</h2>
                <div className="panel-heading-actions">
                  <span>{activeRefreshJobs.length ? `${activeRefreshJobs.length} active` : "Idle"}</span>
                </div>
              </div>
              <div className="settings-controls">
                <div className="settings-field">
                  <span>Display currency</span>
                  <div className="segmented" aria-label="Display currency">
                    <button
                      type="button"
                      className={displayCurrency === "EUR" ? "active" : ""}
                      onClick={() => setDisplayCurrency("EUR")}
                    >
                      EUR
                    </button>
                    <button
                      type="button"
                      className={displayCurrency === "USD" ? "active" : ""}
                      onClick={() => setDisplayCurrency("USD")}
                      disabled={!canShowUsd}
                      title={canShowUsd ? "Show values in USD" : "Refresh market prices to enable USD display"}
                    >
                      USD
                    </button>
                  </div>
                </div>
                <label className="settings-field">
                  <span>Refresh source</span>
                  <select
                    value={refreshSource}
                    onChange={(event) => setRefreshSource(event.target.value as RefreshSource)}
                    disabled={loading}
                    title="Choose source to refresh"
                  >
                    <option value="all">Refresh all</option>
                    <option value="binance">Refresh Binance</option>
                    <option value="ibkr">Refresh IBKR</option>
                    <option value="manual">Refresh manual cash & assets</option>
                    <option value="market_data">Refresh market prices</option>
                  </select>
                </label>
                <button onClick={refresh} disabled={loading || refreshStartPending} title="Refresh selected source">
                  <RefreshCcw size={18} aria-hidden="true" />
                  {refreshStartPending ? "Starting" : "Refresh"}
                </button>
              </div>
            </section>

            <section className="panel settings-panel">
              <div className="panel-heading">
                <div className="panel-title-with-info">
                  <DatabaseZap size={17} aria-hidden="true" />
                  <h2>Source Sync</h2>
                </div>
                <div className="panel-heading-actions">
                  <span>{activeRefreshJobs.length || syncIssueCount}</span>
                </div>
              </div>
              <SourceStatus statuses={sourceSyncStatuses} activeJobs={activeRefreshJobs} summarized />
              {hasIbkrFlex1001Warning && (
                <p className="settings-note">
                  Wait 30-60 minutes and click Refresh IBKR again. If it still returns 1001, try tomorrow morning.
                </p>
              )}
            </section>

            <section className="panel settings-panel">
              <div className="panel-heading">
                <div className="panel-title-with-info">
                  <AlertTriangle size={17} aria-hidden="true" />
                  <h2>Warnings</h2>
                </div>
                <div className="panel-heading-actions">
                  <span>{warningCount}</span>
                </div>
              </div>
              {warningCount ? (
                <DataWarnings warnings={snapshot.data_warnings} />
              ) : (
                <p className="empty block">No data warnings.</p>
              )}
            </section>
          </FrozenPage>
        )}
      </main>
    </div>
  );
}

function App() {
  const [authenticated, setAuthenticated] = useState(loadAppSession);

  const login = useCallback(() => {
    try {
      window.localStorage.setItem(APP_SESSION_STORAGE_KEY, "true");
    } catch {
      // Local storage is only a convenience for this local app gate.
    }
    setAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    try {
      window.localStorage.removeItem(APP_SESSION_STORAGE_KEY);
    } catch {
      // Keep logout functional even if local storage is unavailable.
    }
    setAuthenticated(false);
  }, []);

  if (!authenticated) {
    return <LandingLogin onLogin={login} />;
  }

  return <DashboardApp onLogout={logout} />;
}

export default App;
