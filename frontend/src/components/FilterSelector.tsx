import { Check, Pencil, Plus, SlidersHorizontal, Trash2, X } from "lucide-react";
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
  const rows = isEditing ? filters : filters.filter((filter) => !hiddenKeys.includes(filter.key));
  const hasUnsavedFilter = Boolean(activeName && !activeKey);

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
            <div className="mobile-sheet-handle" aria-hidden="true" />
            <header className="filter-picker-header">
              <h2 id="filter-picker-title">Filter stocks</h2>
              <button type="button" className="filter-picker-mode" disabled={pendingAction !== null} onClick={() => {
                setIsEditing(!isEditing);
                setRenamingKey(null);
                setError(null);
              }}>{isEditing ? "Done" : "Edit"}</button>
            </header>
            <div className="filter-picker-scroll">
              <ul className="filter-picker-list" aria-label="Stock filters">
                <li className="filter-picker-row">
                  {isEditing ? (
                    <div className={`filter-picker-choice ${activeName ? "" : "active"}`}>
                      <span className="filter-picker-name">All stocks</span>
                      <span className="filter-picker-kind">Built-in</span>
                      <span className="filter-picker-selection">{!activeName && <Check size={22} aria-hidden="true" />}</span>
                    </div>
                  ) : (
                    <button type="button" className={`filter-picker-choice ${activeName ? "" : "active"}`} aria-pressed={!activeName}
                      onClick={() => { onClear(); close(); }}>
                      <span className="filter-picker-name">All stocks</span>
                      <span className="filter-picker-kind">Built-in</span>
                      <span className="filter-picker-selection">{!activeName && <Check size={22} aria-hidden="true" />}</span>
                    </button>
                  )}
                </li>
                {rows.map((filter) => (
                  <li className={`filter-picker-row ${isEditing ? "editing" : ""}`} key={filter.key}>
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
                              <span className="filter-picker-name">{filter.name}</span>
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
                        <span className="filter-picker-name">{filter.name}</span>
                        <span className="filter-picker-kind">{filter.isDefault ? "Built-in" : "Custom"}</span>
                        <span className="filter-picker-selection">{activeKey === filter.key && <Check size={22} aria-hidden="true" />}</span>
                      </button>
                    )}
                  </li>
                ))}
                {hasUnsavedFilter && (
                  <li className="filter-picker-row">
                    {isEditing ? (
                      <>
                        <div className="filter-picker-details"><span className="filter-picker-name">{activeName}</span><span className="filter-picker-kind">Custom</span></div>
                        <button type="button" className="filter-picker-icon" title="Edit conditions" aria-label="Edit current filter conditions"
                          disabled={pendingAction !== null} onClick={() => { close(); onEditCurrent(); }}><SlidersHorizontal size={19} /></button>
                      </>
                    ) : (
                      <button type="button" className="filter-picker-choice active" aria-pressed="true" onClick={close}>
                        <span className="filter-picker-name">{activeName}</span><span className="filter-picker-kind">Custom</span>
                        <span className="filter-picker-selection"><Check size={22} aria-hidden="true" /></span>
                      </button>
                    )}
                  </li>
                )}
                {isEditing && (
                  <li className="filter-picker-row">
                    <button type="button" className="filter-picker-new" onClick={() => openBuilder()} disabled={pendingAction !== null}>
                      <Plus size={21} aria-hidden="true" />New filter
                    </button>
                  </li>
                )}
              </ul>
              {error && <p className="mobile-personal-error" role="alert">{error}</p>}
              {pendingAction && <p className="filter-picker-hint" role="status">{pendingAction === "delete" ? "Deleting filter…" : "Saving name…"}</p>}
            </div>
          </div>
        </dialog>
      )}
    </>
  );
}
