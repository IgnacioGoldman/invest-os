import { ArrowLeft, Check, ChevronDown, Pencil, Plus, SlidersHorizontal, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import "../filterSelector.css";

export type FilterShortcut = {
  key: string;
  name: string;
  isDefault: boolean;
  badgeCount?: number;
};

type Props = {
  userId: string | null;
  filters: FilterShortcut[];
  activeKey: string | null;
  activeName: string | null;
  onSelect: (key: string) => void;
  onClear: () => void;
  onCreate: () => void;
  onEditCurrent: () => void;
  onEdit: (key: string) => void;
  onDelete: (key: string) => Promise<void>;
};

function readHiddenFilters(storageKey: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    return Array.isArray(value) ? value.filter((key): key is string => typeof key === "string") : [];
  } catch {
    return [];
  }
}

export function FilterSelector({ userId, filters, activeKey, activeName, onSelect, onClear, onCreate, onEditCurrent, onEdit, onDelete }: Props) {
  const storageKey = `invest-os:filter-visibility:${userId ?? "guest"}`;
  const [hiddenKeys, setHiddenKeys] = useState(() => readHiddenFilters(storageKey));
  const [view, setView] = useState<"choose" | "manage" | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const selectorRef = useRef<HTMLButtonElement>(null);
  const mutationRef = useRef(false);
  const visibleFilters = filters.filter((filter) => !hiddenKeys.includes(filter.key));
  const isOpen = view !== null;

  useEffect(() => {
    if (!isOpen) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog?.showModal();
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      selectorRef.current?.focus({ preventScroll: true });
    };
  }, [isOpen]);

  const close = () => {
    if (!mutationRef.current) setView(null);
  };

  const toggleVisibility = (key: string) => {
    const next = hiddenKeys.includes(key) ? hiddenKeys.filter((item) => item !== key) : [...hiddenKeys, key];
    setHiddenKeys(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // Visibility still works for this visit when browser storage is unavailable.
    }
  };

  const deleteFilter = async (key: string) => {
    if (mutationRef.current) return;
    mutationRef.current = true;
    setDeletingKey(key);
    setError(null);
    try {
      await onDelete(key);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not delete this filter. Please try again.");
    } finally {
      mutationRef.current = false;
      setDeletingKey(null);
    }
  };

  const openBuilder = (key?: string) => {
    setView(null);
    if (key) onEdit(key);
    else onCreate();
  };

  const renderSection = (isDefault: boolean) => {
    const rows = (view === "manage" ? filters : visibleFilters).filter((filter) => filter.isDefault === isDefault);
    if (view === "choose" && isDefault && rows.length === 0) return null;
    return (
      <section className="filter-picker-section" aria-label={isDefault ? "Default filters" : "My filters"}>
        <div className="filter-picker-heading">
          <h3>{isDefault ? "Default" : "My filters"}</h3>
          {view === "manage" && isDefault && <span>Show</span>}
          {!isDefault && <button type="button" className="filter-picker-new" onClick={() => openBuilder()} disabled={deletingKey !== null}><Plus size={18} />New</button>}
        </div>
        {rows.length > 0 ? (
          <div className="filter-picker-list">
            {rows.map((filter) => (
              <div className="filter-picker-row" key={filter.key}>
                {view === "choose" ? (
                  <button type="button" className={`filter-picker-choice ${activeKey === filter.key ? "active" : ""}`}
                    aria-pressed={activeKey === filter.key} onClick={() => { onSelect(filter.key); close(); }}>
                    <span>{filter.name}</span>
                    {Boolean(filter.badgeCount) && <span className="mobile-filter-new-badge">+{filter.badgeCount}</span>}
                    {activeKey === filter.key && <Check size={20} aria-hidden="true" />}
                  </button>
                ) : (
                  <>
                    <span className="filter-picker-name">{filter.name}</span>
                    <div className="filter-picker-controls">
                      <button type="button" className="filter-picker-visibility" role="switch" aria-checked={!hiddenKeys.includes(filter.key)}
                        aria-label={`Show ${filter.name} in filter selector`} disabled={deletingKey !== null} onClick={() => toggleVisibility(filter.key)}>
                        <span className={hiddenKeys.includes(filter.key) ? "" : "visible"}>{!hiddenKeys.includes(filter.key) && <Check size={17} strokeWidth={3} />}</span>
                      </button>
                      {!isDefault && (
                        <>
                          <button type="button" className="filter-picker-icon" aria-label={`Edit ${filter.name}`} disabled={deletingKey !== null} onClick={() => openBuilder(filter.key)}><Pencil size={19} /></button>
                          <button type="button" className="filter-picker-icon" aria-label={`Delete ${filter.name}`} disabled={deletingKey !== null} onClick={() => void deleteFilter(filter.key)}><Trash2 size={19} /></button>
                        </>
                      )}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="filter-picker-empty">{filters.some((filter) => !filter.isDefault) ? "Your filters are hidden. Show them in Manage filters." : "Create a filter with your own conditions."}</p>
        )}
      </section>
    );
  };

  return (
    <>
      <div className="filter-selector-row">
        <button ref={selectorRef} type="button" className={`filter-selector ${activeName ? "active" : ""}`} aria-haspopup="dialog" aria-expanded={isOpen}
          aria-label={`Choose filter, ${activeName ?? "all stocks"}`} onClick={() => { setError(null); setView("choose"); }}>
          <SlidersHorizontal size={21} aria-hidden="true" />
          <span className="filter-selector-copy"><small>Filter</small><strong>{activeName ?? "All stocks"}</strong></span>
          <ChevronDown size={20} aria-hidden="true" />
        </button>
        {activeName && <button type="button" className="filter-selector-clear" onClick={onClear}>Clear</button>}
      </div>
      {isOpen && (
        <dialog ref={dialogRef} className="filter-picker-sheet" aria-label={view === "manage" ? "Manage filters" : "Choose a filter"}
          onCancel={(event) => { event.preventDefault(); close(); }}
          onClick={(event) => { if (event.currentTarget === event.target) close(); }}>
          <div className="filter-picker-content">
            <div className="mobile-sheet-handle" aria-hidden="true" />
            <header className="filter-picker-header">
              {view === "manage" && <button type="button" className="filter-picker-icon" aria-label="Back to filter selector" onClick={() => setView("choose")} disabled={deletingKey !== null}><ArrowLeft size={20} /></button>}
              <h2>{view === "manage" ? "Manage filters" : "Choose a filter"}</h2>
              <span>{userId ? "Watchlist" : "Stocks"}</span>
              <button type="button" className="filter-picker-icon" aria-label="Close filters" onClick={close} disabled={deletingKey !== null}><X size={21} /></button>
            </header>
            <div className="filter-picker-scroll">
              {view === "choose" && <button type="button" className={`filter-picker-all ${activeName ? "" : "active"}`} aria-pressed={!activeName}
                onClick={() => { onClear(); close(); }}>All stocks{!activeName && <Check size={20} />}</button>}
              {view === "choose" && activeName && !activeKey && <button type="button" className="filter-picker-all"
                onClick={() => { setView(null); onEditCurrent(); }}>Edit current filter<Pencil size={18} /></button>}
              {renderSection(true)}
              {renderSection(false)}
              {error && <p className="mobile-personal-error" role="alert">{error}</p>}
              {deletingKey && <p className="filter-picker-hint" role="status">Deleting filter…</p>}
            </div>
            <footer className="filter-picker-footer">
              {view === "choose" ? (
                <button type="button" className="filter-picker-manage" onClick={() => setView("manage")}><SlidersHorizontal size={18} />Manage filters</button>
              ) : (
                <><p>Show or hide filters in the selector. Your active filter stays applied.</p><button type="button" className="filter-picker-done" onClick={close} disabled={deletingKey !== null}>Done</button></>
              )}
            </footer>
          </div>
        </dialog>
      )}
    </>
  );
}
