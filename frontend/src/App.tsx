import type { Session } from "@supabase/supabase-js";
import { Pencil, Plus, RefreshCcw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchOpenDataStocks,
  fetchRefreshJobs,
  fetchStockUniverse,
  addActiveStock,
  removeActiveStock,
  startRefreshJob,
  STATIC_DATA_MODE,
  type OpenDataStockSnapshot,
  type RefreshJob,
  type StockUniverseItem,
} from "./api";
import { MobileStockExplorer } from "./components/MobileStockExplorer";
import { PersonalizationControls } from "./components/PersonalizationControls";
import {
  deleteSavedFilter,
  fetchNotifications,
  fetchSavedFilters,
  markAllNotificationsRead,
  markNotificationRead,
  saveFilter,
  type SavedFilter,
  type SaveFilterInput,
  type StockNotification,
} from "./personalization";
import { isSupabaseConfigured, signInWithGoogle, signOut, supabase } from "./supabase";
import "./styles.css";

const isActiveRefreshJob = (job: RefreshJob) => job.status === "queued" || job.status === "running";
const isExplorationBetaRefreshJob = (job: RefreshJob) => job.source === "exploration_beta";

export default function App() {
  const [stocks, setStocks] = useState<OpenDataStockSnapshot[]>([]);
  const [selectedTicker, setSelectedTicker] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshJobs, setRefreshJobs] = useState<RefreshJob[]>([]);
  const [universe, setUniverse] = useState<StockUniverseItem[]>([]);
  const [stockPickerOpen, setStockPickerOpen] = useState(false);
  const [stockSearch, setStockSearch] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [mutatingTicker, setMutatingTicker] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [notifications, setNotifications] = useState<StockNotification[]>([]);

  const loadStocks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchOpenDataStocks();
      setStocks(rows);
      setSelectedTicker((current) => current || rows[0]?.ticker || "");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to load Exploration Beta data.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      setRefreshJobs(await fetchRefreshJobs());
    } catch {
      // Refresh status is helpful, but the table can still work without it.
    }
  }, []);

  const loadUniverse = useCallback(async () => {
    try {
      setUniverse(await fetchStockUniverse());
    } catch {
      // The table can still render even if the add-stock catalog is unavailable.
    }
  }, []);

  useEffect(() => {
    void loadStocks();
    void loadJobs();
    void loadUniverse();
  }, [loadJobs, loadStocks, loadUniverse]);

  useEffect(() => {
    if (!supabase) return undefined;
    let mounted = true;
    void supabase.auth.getSession().then(({ data, error: authError }) => {
      if (!mounted) return;
      if (authError) setError(authError.message);
      setSession(data.session);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (mounted) setSession(nextSession);
    });
    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  const loadPersonalization = useCallback(async (userId: string) => {
    try {
      const [filters, items] = await Promise.all([
        fetchSavedFilters(userId),
        fetchNotifications(userId),
      ]);
      setSavedFilters(filters);
      setNotifications(items);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to load your saved filters.");
    }
  }, []);

  useEffect(() => {
    if (!session) {
      setSavedFilters([]);
      setNotifications([]);
      return undefined;
    }
    void loadPersonalization(session.user.id);
    const refreshOnFocus = () => {
      if (document.visibilityState === "visible") void loadPersonalization(session.user.id);
    };
    document.addEventListener("visibilitychange", refreshOnFocus);
    return () => document.removeEventListener("visibilitychange", refreshOnFocus);
  }, [loadPersonalization, session]);

  const activeRefresh = useMemo(
    () => refreshJobs.find((job) => isExplorationBetaRefreshJob(job) && isActiveRefreshJob(job)) ?? null,
    [refreshJobs],
  );

  useEffect(() => {
    if (!activeRefresh) return undefined;
    const interval = window.setInterval(() => {
      void loadJobs();
      void loadStocks();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [activeRefresh, loadJobs, loadStocks]);

  const refreshBeta = async () => {
    setError(null);
    try {
      const job = await startRefreshJob("exploration_beta");
      setRefreshJobs((jobs) => [job, ...jobs.filter((item) => item.id !== job.id)]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to start Exploration Beta refresh.");
    }
  };

  const addStock = async (ticker: string) => {
    setError(null);
    setMutatingTicker(ticker);
    try {
      const snapshot = await addActiveStock(ticker);
      setStocks((current) => {
        const existing = current.filter((item) => item.ticker !== snapshot.ticker);
        return [...existing, snapshot].sort((left, right) => left.ticker.localeCompare(right.ticker));
      });
      setSelectedTicker(snapshot.ticker);
      setStockPickerOpen(false);
      setStockSearch("");
      await loadUniverse();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : `Failed to add ${ticker}.`);
    } finally {
      setMutatingTicker(null);
    }
  };

  const removeStock = async (ticker: string) => {
    setError(null);
    setMutatingTicker(ticker);
    try {
      await removeActiveStock(ticker);
      setStocks((current) => {
        const next = current.filter((item) => item.ticker !== ticker);
        setSelectedTicker((selected) => (selected === ticker ? next[0]?.ticker ?? "" : selected));
        return next;
      });
      await loadUniverse();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : `Failed to remove ${ticker}.`);
    } finally {
      setMutatingTicker(null);
    }
  };

  const persistFilter = async (input: Omit<SaveFilterInput, "userId">) => {
    if (!session) throw new Error("Sign in before saving a filter.");
    const saved = await saveFilter({ ...input, userId: session.user.id });
    setSavedFilters((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
    return saved;
  };

  const removeSavedFilter = async (filterId: string) => {
    await deleteSavedFilter(filterId);
    setSavedFilters((current) => current.filter((item) => item.id !== filterId));
    setNotifications((current) => current.filter((item) => item.filter_id !== filterId));
  };

  const readNotification = async (notificationId: string) => {
    await markNotificationRead(notificationId);
    const readAt = new Date().toISOString();
    setNotifications((current) => current.map((item) => item.id === notificationId ? { ...item, read_at: readAt } : item));
  };

  const readAllNotifications = async () => {
    if (!session) return;
    await markAllNotificationsRead(session.user.id);
    const readAt = new Date().toISOString();
    setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? readAt })));
  };

  const stockSearchNeedle = stockSearch.trim().toLowerCase();
  const stockSearchResults = universe
    .filter((item) => {
      if (!stockSearchNeedle) return true;
      return [item.symbol, item.name, item.sector, item.industry]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(stockSearchNeedle));
    })
    .slice(0, 30);

  const betaActions = STATIC_DATA_MODE ? null : (
    <div className="stock-action-cluster">
      <button
        type="button"
        className="button"
        onClick={() => setStockPickerOpen((open) => !open)}
        title="Add stock"
        aria-expanded={stockPickerOpen}
      >
        <Plus size={16} aria-hidden="true" />
        Add
      </button>
      <button
        type="button"
        className={`button ${editMode ? "active" : ""}`}
        onClick={() => setEditMode((active) => !active)}
        title="Edit table stocks"
        aria-pressed={editMode}
      >
        <Pencil size={16} aria-hidden="true" />
        Edit
      </button>
      <button
        type="button"
        className="button primary"
        onClick={refreshBeta}
        disabled={Boolean(activeRefresh)}
        title="Fetch missing or stale stock data and rebuild beta table data"
      >
        <RefreshCcw size={16} aria-hidden="true" />
        {activeRefresh ? activeRefresh.stage : "Refresh"}
      </button>
      {stockPickerOpen && (
        <div className="stock-picker-popover">
          <div className="stock-picker-heading">
            <strong>Add stock</strong>
            <button type="button" className="icon-button" onClick={() => setStockPickerOpen(false)} title="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>
          <input
            type="search"
            value={stockSearch}
            onChange={(event) => setStockSearch(event.target.value)}
            placeholder="Search symbol, name, sector"
            aria-label="Search stock universe"
            autoFocus
          />
          <div className="stock-picker-list">
            {stockSearchResults.map((item) => {
              const activeAndLoaded = item.active && item.loaded;
              const disabled = activeAndLoaded || mutatingTicker === item.symbol;
              return (
                <button
                  type="button"
                  key={item.symbol}
                  disabled={disabled}
                  onClick={() => addStock(item.symbol)}
                  title={activeAndLoaded ? "Already in table" : `Add ${item.symbol}`}
                >
                  <span>
                    <strong>{item.symbol}</strong>
                    <small>{item.name ?? item.industry ?? "-"}</small>
                  </span>
                  <em>
                    {activeAndLoaded
                      ? "Added"
                      : mutatingTicker === item.symbol
                        ? "Adding"
                        : item.active
                          ? "Fetch"
                          : item.sector ?? "Add"}
                  </em>
                </button>
              );
            })}
            {stockSearchResults.length === 0 && <p className="empty block">No stocks match the search.</p>}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="stock-mobile-shell">
      <main className="stock-mobile-page">
        {error && <p className="error-banner">{error}</p>}
        <MobileStockExplorer
          snapshots={stocks}
          selectedTicker={selectedTicker}
          loading={loading}
          onSelectTicker={setSelectedTicker}
          actions={betaActions}
          headerActions={(openTicker) => (
            <PersonalizationControls
              configured={isSupabaseConfigured}
              session={session}
              notifications={notifications}
              onSignIn={signInWithGoogle}
              onSignOut={signOut}
              onReadNotification={readNotification}
              onReadAllNotifications={readAllNotifications}
              onOpenTicker={openTicker}
            />
          )}
          personalization={isSupabaseConfigured ? {
            signedIn: Boolean(session),
            savedFilters,
            onRequestSignIn: signInWithGoogle,
            onSaveFilter: persistFilter,
            onDeleteFilter: removeSavedFilter,
          } : undefined}
          editMode={STATIC_DATA_MODE ? false : editMode}
          removingTicker={mutatingTicker}
          onRemoveStock={removeStock}
        />
      </main>
    </div>
  );
}
