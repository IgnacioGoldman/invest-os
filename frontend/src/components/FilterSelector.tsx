import { CalendarDays, ChartNoAxesCombined, Check, Layers3, Pencil, Plus, SlidersHorizontal, Trash2, TrendingUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import "../filterSelector.css";

export type FilterShortcut = {
  key: string;
  name: string;
  isDefault: boolean;
  badgeCount?: number;
  identity?: "support" | "pullback" | "earnings";
  description?: string;
};

function FilterIdentity({ filter, allStocks = false }: { filter?: FilterShortcut; allStocks?: boolean }) {
  const identity = allStocks ? "all" : filter?.identity ?? "custom";
  const Icon = identity === "all" ? Layers3 : identity === "support" ? TrendingUp
    : identity === "pullback" ? ChartNoAxesCombined : identity === "earnings" ? CalendarDays : SlidersHorizontal;
  // Keep a custom filter's accent stable across renames and list reordering.
  const accent = identity === "custom"
    ? `custom-${Array.from(filter?.key ?? "").reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 0) % 3}`
    : identity;
  return <>
    <span className={`filter-picker-avatar filter-accent-${accent}`} aria-hidden="true"><Icon size={23} strokeWidth={1.8} /></span>
    <span className="filter-picker-copy">
      <span className="filter-picker-name">{allStocks ? "All stocks" : filter?.name}</span>
      <span className="filter-picker-description">{allStocks ? "Explore every company" : filter?.description ?? "Your saved screening conditions"}</span>
    </span>
  </>;
}

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
  onRename: (key: string, name: string) => Promise<void>;
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

export function FilterSelector({ userId, filters, activeKey, activeName, onSelect, onClear, onCreate, onEditCurrent, onEdit, onRename, onDelete }: Props) {
  const storageKey = `invest-os:filter-visibility:${userId ?? "guest"}`;
  const [hiddenKeys, setHiddenKeys] = useState(() => readHiddenFilters(storageKey));
  const [isOpen, setIsOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [renamingKey, setRenamingKey] = useState<string | null>(null);
  const [renameName, setRenameName] = useState("");
  const [pendingAction, setPendingAction] = useState<"rename" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const selectorRef = useRef<HTMLButtonElement>(null);
  const mutationRef = useRef(false);
  const swipeRef = useRef<{ x: number; y: number } | null>(null);
  const rows = isEditing ? filters : filters.filter((filter) => !hiddenKeys.includes(filter.key));
  const hasUnsavedFilter = Boolean(activeName && !activeKey);

  useEffect(() => {
    if (!isOpen) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog?.showModal();
    dialog?.querySelector<HTMLElement>("#filter-picker-title")?.focus({ preventScroll: true });
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      selectorRef.current?.focus({ preventScroll: true });
    };
  }, [isOpen]);

  const close = () => {
    if (!mutationRef.current) setIsOpen(false);
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
    setPendingAction("delete");
    setError(null);
    try {
      await onDelete(key);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not delete this filter. Please try again.");
    } finally {
      mutationRef.current = false;
      setPendingAction(null);
    }
  };

  const renameFilter = async () => {
    const name = renameName.trim();
    if (!renamingKey || !name || mutationRef.current) return;
    mutationRef.current = true;
    setPendingAction("rename");
    setError(null);
    try {
      await onRename(renamingKey, name);
      setRenamingKey(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not rename this filter. Please try again.");
    } finally {
      mutationRef.current = false;
      setPendingAction(null);
    }
  };

  const openBuilder = (key?: string) => {
    close();
    if (key) onEdit(key);
    else onCreate();
  };

  return (
    <>
      <div className="filter-selector-row" role="group" aria-label="Stock filters">
        <button ref={selectorRef} type="button" className="filter-selector" aria-haspopup="dialog" aria-expanded={isOpen}
          aria-label={`Filters, ${activeName ? `1 active filter: ${activeName}` : "no active filters"}`} onClick={() => {
            setError(null);
            setIsEditing(false);
            setRenamingKey(null);
            setIsOpen(true);
          }}>
          <SlidersHorizontal size={18} aria-hidden="true" />
          <span>Filters</span>
          {activeName && <span className="filter-selector-count" aria-hidden="true">1</span>}
        </button>
        {activeName && <button type="button" className="filter-selector-chip" aria-label={`Remove ${activeName} filter`}
          onClick={() => { onClear(); selectorRef.current?.focus({ preventScroll: true }); }}>
          <span>{activeName}</span><X size={16} aria-hidden="true" />
        </button>}
      </div>
      {isOpen && (
        <dialog ref={dialogRef} className="filter-picker-sheet" aria-labelledby="filter-picker-title"
          onCancel={(event) => { event.preventDefault(); close(); }}
          onClick={(event) => { if (event.currentTarget === event.target) close(); }}>
          <div className="filter-picker-content">
            <div className="filter-picker-drag-area"
              onTouchStart={(event) => {
                const touch = event.touches[0];
                swipeRef.current = event.touches.length === 1 ? { x: touch.clientX, y: touch.clientY } : null;
              }}
              onTouchEnd={(event) => {
                const start = swipeRef.current;
                swipeRef.current = null;
                const touch = event.changedTouches[0];
                if (start && touch.clientY - start.y > 60 && Math.abs(touch.clientX - start.x) < 60) close();
              }}
              onTouchCancel={() => { swipeRef.current = null; }}>
            <div className="mobile-sheet-handle" aria-hidden="true" />
            <header className="filter-picker-header">
              <h2 id="filter-picker-title" tabIndex={-1}>Filter stocks</h2>
              <button type="button" className="filter-picker-mode" aria-pressed={isEditing} disabled={pendingAction !== null} onClick={() => {
                setIsEditing(!isEditing);
                setRenamingKey(null);
                setError(null);
              }}>{isEditing ? <Check size={18} aria-hidden="true" /> : <Pencil size={18} aria-hidden="true" />}{isEditing ? "Done" : "Edit"}</button>
              <button type="button" className="filter-picker-icon filter-picker-close" aria-label="Close filters"
                disabled={pendingAction !== null} onClick={close}><X size={22} aria-hidden="true" /></button>
            </header>
            </div>
            <div className="filter-picker-scroll">
              <ul className="filter-picker-list" aria-label="Stock filters">
                <li className="filter-picker-row">
                  {isEditing ? (
                    <div className={`filter-picker-choice ${activeName ? "" : "active"}`}>
                      <FilterIdentity allStocks />
                      <span className="filter-picker-meta"><span className="filter-picker-kind">Built-in</span>
                        <span className="filter-picker-kind">Always shown</span></span>
                    </div>
                  ) : (
                    <button type="button" className={`filter-picker-choice ${activeName ? "" : "active"}`} aria-pressed={!activeName}
                      onClick={() => { onClear(); close(); }}>
                      <FilterIdentity allStocks />
                      <span className="filter-picker-meta"><span className="filter-picker-kind">Built-in</span>
                        {!activeName && <Check size={20} aria-hidden="true" />}</span>
                    </button>
                  )}
                </li>
                {rows.map((filter) => (
                  <li className={`filter-picker-row ${isEditing ? "editing" : ""} ${isEditing && hiddenKeys.includes(filter.key) ? "is-hidden" : ""}`} key={filter.key}>
                    {isEditing ? (
                      <>
                        {renamingKey === filter.key ? (
                          <form className="filter-picker-rename" onSubmit={(event) => { event.preventDefault(); void renameFilter(); }}>
                            <input aria-label={`New name for ${filter.name}`} value={renameName} autoFocus maxLength={120}
                              disabled={pendingAction !== null} onChange={(event) => setRenameName(event.target.value)} />
                            <button type="submit" className="filter-picker-icon" title="Save name" aria-label="Save filter name"
                              disabled={pendingAction !== null || !renameName.trim()}><Check size={20} /></button>
                            <button type="button" className="filter-picker-icon" title="Cancel rename" aria-label="Cancel rename"
                              disabled={pendingAction !== null} onClick={() => { setRenamingKey(null); setError(null); }}><X size={20} /></button>
                          </form>
                        ) : (
                          <>
                            <div className="filter-picker-details">
                              <FilterIdentity filter={filter} />
                              <span className="filter-picker-kind">{filter.isDefault ? "Built-in" : "Custom"}</span>
                            </div>
                            <div className="filter-picker-controls">
                              <button type="button" className="filter-picker-visibility" role="switch" aria-checked={!hiddenKeys.includes(filter.key)}
                                aria-label={`Show ${filter.name} in filter selector`} title={hiddenKeys.includes(filter.key) ? "Show filter" : "Hide filter"}
                                disabled={pendingAction !== null} onClick={() => toggleVisibility(filter.key)}>
                                <span className={hiddenKeys.includes(filter.key) ? "" : "visible"}><span /></span>
                              </button>
                              {!filter.isDefault && (
                                <>
                                  <button type="button" className="filter-picker-icon" title="Rename filter" aria-label={`Rename ${filter.name}`}
                                    disabled={pendingAction !== null} onClick={() => { setRenamingKey(filter.key); setRenameName(filter.name); setError(null); }}><Pencil size={19} /></button>
                                  <button type="button" className="filter-picker-icon" title="Edit conditions" aria-label={`Edit conditions for ${filter.name}`}
                                    disabled={pendingAction !== null} onClick={() => openBuilder(filter.key)}><SlidersHorizontal size={19} /></button>
                                  <button type="button" className="filter-picker-icon filter-picker-delete" title="Delete filter" aria-label={`Delete ${filter.name}`}
                                    disabled={pendingAction !== null} onClick={() => void deleteFilter(filter.key)}><Trash2 size={19} /></button>
                                </>
                              )}
                            </div>
                          </>
                        )}
                      </>
                    ) : (
                      <button type="button" className={`filter-picker-choice ${activeKey === filter.key ? "active" : ""}`}
                        aria-pressed={activeKey === filter.key} onClick={() => { onSelect(filter.key); close(); }}>
                        <FilterIdentity filter={filter} />
                        <span className="filter-picker-meta"><span className="filter-picker-kind">{filter.isDefault ? "Built-in" : "Custom"}</span>
                          {activeKey === filter.key && <Check size={20} aria-hidden="true" />}</span>
                      </button>
                    )}
                  </li>
                ))}
                {hasUnsavedFilter && (
                  <li className={`filter-picker-row ${isEditing ? "editing" : ""}`}>
                    {isEditing ? (
                      <>
                        <div className="filter-picker-details"><FilterIdentity filter={{ key: "unsaved", name: activeName ?? "Custom filter", isDefault: false, description: "Your current screening conditions" }} /><span className="filter-picker-kind">Custom</span></div>
                        <button type="button" className="filter-picker-icon" title="Edit conditions" aria-label="Edit current filter conditions"
                          disabled={pendingAction !== null} onClick={() => { close(); onEditCurrent(); }}><SlidersHorizontal size={19} /></button>
                      </>
                    ) : (
                      <button type="button" className="filter-picker-choice active" aria-pressed="true" onClick={close}>
                        <FilterIdentity filter={{ key: "unsaved", name: activeName ?? "Custom filter", isDefault: false, description: "Your current screening conditions" }} />
                        <span className="filter-picker-meta"><span className="filter-picker-kind">Custom</span><Check size={20} aria-hidden="true" /></span>
                      </button>
                    )}
                  </li>
                )}
              </ul>
              {error && <p className="mobile-personal-error" role="alert">{error}</p>}
              {pendingAction && <p className="filter-picker-hint" role="status">{pendingAction === "delete" ? "Deleting filter…" : "Saving name…"}</p>}
            </div>
            <footer className="filter-picker-footer">
              <button type="button" className="filter-picker-new" onClick={() => openBuilder()} disabled={pendingAction !== null}>
                <Plus size={21} aria-hidden="true" />New filter
              </button>
            </footer>
          </div>
        </dialog>
      )}
    </>
  );
}
