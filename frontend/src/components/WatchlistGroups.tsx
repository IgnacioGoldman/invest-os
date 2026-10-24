import { ArrowDown, ArrowUp, BookmarkCheck, Check, ChevronDown, ChevronRight, GripVertical, MoreHorizontal, Plus, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { WATCHLIST_COLORS, type WatchlistGroup, type WatchlistGroupInput, type WatchlistItem } from "../watchlist";
import type { OpenDataStockSnapshot } from "../api";

export type WatchlistGroupActions = {
  onMoveWatchlistItem: (ticker: string, groupId: string | null, beforeTicker?: string) => Promise<void>;
  onCreateWatchlistGroup: (input: WatchlistGroupInput) => Promise<void>;
  onUpdateWatchlistGroup: (id: string, input: Partial<WatchlistGroupInput & { collapsed: boolean }>) => Promise<void>;
  onDeleteWatchlistGroup: (id: string) => Promise<void>;
};

// Native dialogs supply focus trapping, Escape dismissal and focus restoration.
export function WatchlistDialog({ title, onClose, children, className = "" }: { title: string; onClose: () => void; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog ref={ref} className={`watchlist-dialog ${className}`} aria-label={title}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]',
        )).filter((control) => control.getClientRects().length > 0);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="watchlist-dialog-content">
        <header><h2>{title}</h2><button type="button" className="watchlist-icon" aria-label={`Close ${title}`} onClick={onClose}><X size={20} /></button></header>
        {children}
      </div>
    </dialog>
  );
}

type Drag = { id: string; label: string; x: number; y: number; active: boolean };
type Target = { groupId: string | null; ticker?: string; beforeTicker?: string; after?: boolean };

export function WatchlistGroups({
  groups, items, matchingSnapshots, pagedSnapshots, renderRow, onRevealGroup,
  onManualOrder, onRemove, actions, organizing,
}: {
  groups: WatchlistGroup[];
  items: WatchlistItem[];
  matchingSnapshots: OpenDataStockSnapshot[];
  pagedSnapshots: OpenDataStockSnapshot[];
  renderRow: (snapshot: OpenDataStockSnapshot) => ReactNode;
  onRevealGroup: (groupId: string | null) => void;
  onManualOrder: () => void;
  onRemove: (ticker: string) => Promise<void>;
  actions: WatchlistGroupActions;
  organizing: boolean;
}) {
  const [editor, setEditor] = useState<WatchlistGroup | "new" | null>(null);
  const [name, setName] = useState("");
  const [movingTicker, setMovingTicker] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [drag, setDrag] = useState<Drag | null>(null);
  const dragRef = useRef<Drag | null>(null);
  const suppressClick = useRef(false);
  const origin = useRef({ x: 0, y: 0 });
  const [target, setTarget] = useState<Target | null>(null);
  const targetRef = useRef<Target | null>(null);
  const orderedGroups = [...groups].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id));
  const itemByTicker = useMemo(() => new Map(items.map((item) => [item.ticker, item])), [items]);
  const groupFor = (ticker: string) => itemByTicker.get(ticker)?.group_id ?? null;
  const currentItem = items.find((item) => item.ticker === movingTicker);
  const siblings = [...items].sort((a, b) => a.position - b.position).filter((item) => item.group_id === currentItem?.group_id);
  const siblingIndex = siblings.findIndex((item) => item.ticker === movingTicker);

  const run = async (action: () => Promise<void>, message: string, close = false) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await action();
      setAnnouncement(message);
      if (close) { setEditor(null); setMovingTicker(null); }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save your change. Please try again.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const openEditor = (group?: WatchlistGroup) => {
    setError(null);
    setName(group?.name ?? "");
    setEditor(group ?? "new");
  };

  const resetDrag = () => {
    dragRef.current = null;
    targetRef.current = null;
    setDrag(null);
    setTarget(null);
  };

  const locateTarget = (x: number, y: number) => {
    const section = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-watchlist-group]");
    let next: Target | null = null;
    if (section) {
      const groupId = section.dataset.watchlistGroup || null;
      const row = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-watchlist-ticker]");
      next = { groupId, ticker: row?.dataset.watchlistTicker };
      if (row) {
        const bounds = row.getBoundingClientRect();
        const ticker = row.dataset.watchlistTicker;
        next.after = y > bounds.top + bounds.height / 2;
        const siblings = [...items].filter((item) => item.group_id === groupId).sort((a, b) => a.position - b.position);
        const index = siblings.findIndex((item) => item.ticker === ticker);
        next.beforeTicker = next.after ? siblings[index + 1]?.ticker : ticker;
      }
    }
    targetRef.current = next;
    setTarget(next);
  };

  useEffect(() => {
    if (!drag?.active) return;
    let frame = 0;
    const scroll = () => {
      const current = dragRef.current;
      if (!current?.active) return;
      const delta = current.y < 80 ? -10 : current.y > window.innerHeight - 80 ? 10 : 0;
      if (delta) { window.scrollBy(0, delta); locateTarget(current.x, current.y); }
      frame = requestAnimationFrame(scroll);
    };
    frame = requestAnimationFrame(scroll);
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") resetDrag(); };
    document.addEventListener("keydown", escape);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("keydown", escape); };
  }, [drag?.active]);

  const startDrag = (event: PointerEvent<HTMLButtonElement>, id: string, label: string) => {
    if (busy || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    origin.current = { x: event.clientX, y: event.clientY };
    suppressClick.current = false;
    dragRef.current = { id, label, x: event.clientX, y: event.clientY, active: false };
  };
  const moveDrag = (event: PointerEvent<HTMLButtonElement>) => {
    const current = dragRef.current;
    if (!current) return;
    const active = current.active || Math.hypot(event.clientX - origin.current.x, event.clientY - origin.current.y) > 6;
    const next = { ...current, x: event.clientX, y: event.clientY, active };
    dragRef.current = next;
    setDrag(next);
    if (active) { event.preventDefault(); locateTarget(event.clientX, event.clientY); }
  };
  const finishDrag = () => {
    const current = dragRef.current;
    const destination = targetRef.current;
    suppressClick.current = Boolean(current?.active);
    resetDrag();
    if (!current?.active || !destination) return;
    if (current.id !== destination.ticker) {
      void run(async () => {
        await actions.onMoveWatchlistItem(current.id, destination.groupId, destination.beforeTicker);
        onManualOrder();
      }, `${current.label} moved.`);
    }
  };
  const grip = (id: string, label: string) => (
    <button type="button" className="watchlist-icon watchlist-grip" disabled={busy}
      aria-label={`Reorder ${label}`} title="Drag to reorder, or click to move or remove"
      onPointerDown={(event) => startDrag(event, id, label)} onPointerMove={moveDrag}
      onPointerUp={finishDrag} onPointerCancel={resetDrag} onLostPointerCapture={resetDrag}
      onClick={() => {
        if (suppressClick.current) { suppressClick.current = false; return; }
        setError(null);
        setMovingTicker(id);
      }}>
      <GripVertical size={16} />
    </button>
  );

  const moveSymbol = (groupId: string | null, beforeTicker?: string) => {
    if (!movingTicker) return;
    void run(async () => {
      await actions.onMoveWatchlistItem(movingTicker, groupId, beforeTicker);
      onManualOrder();
    }, `${movingTicker} moved.`, true);
  };

  const editorGroup = editor && editor !== "new" ? groups.find((group) => group.id === editor.id) ?? editor : null;
  const sections: Array<WatchlistGroup | null> = [...orderedGroups, null];

  return (
    <div className={`watchlist-groups${organizing ? " watchlist-organizing" : ""}${groups.length === 0 ? " watchlist-flat" : ""}`} aria-busy={busy}>
      {organizing && <div className="watchlist-group-toolbar">
        <button type="button" className="watchlist-action" disabled={busy} onClick={() => openEditor()}><Plus size={18} aria-hidden="true" />New group</button>
      </div>}
      {error && !editor && !movingTicker && <p className="watchlist-error" role="alert">{error}</p>}
      <span className="watchlist-sr-only" role="status" aria-live="polite">{announcement}</span>
      {sections.map((group) => {
        const id = group?.id ?? null;
        const label = group?.name ?? "Ungrouped";
        const total = items.filter((item) => groupFor(item.ticker) === id).length;
        const matching = matchingSnapshots.filter((snapshot) => groupFor(snapshot.ticker) === id);
        const rows = pagedSnapshots.filter((snapshot) => groupFor(snapshot.ticker) === id);
        const dropping = Boolean(drag?.active && target && target.groupId === id);
        if (!group && groups.length > 0 && total === 0 && !organizing) return null;
        return (
          <section key={id ?? "ungrouped"} data-watchlist-group={id ?? ""}
            className={`watchlist-group${group ? "" : " watchlist-ungrouped"}${dropping ? " watchlist-drop-target" : ""}`}
            aria-label={label}>
            {(group || groups.length > 0) && <header className="watchlist-group-header">
              {group ? (
                <button type="button" className="watchlist-group-toggle" aria-expanded={!group.collapsed}
                  aria-controls={`watchlist-group-${id}`} disabled={busy}
                  onClick={() => void run(() => actions.onUpdateWatchlistGroup(group.id, { collapsed: !group.collapsed }), `${label} ${group.collapsed ? "expanded" : "collapsed"}.`)}>
                  {group.collapsed ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                  <strong>{label}</strong>
                </button>
              ) : <div className="watchlist-ungrouped-label"><strong>{label}</strong></div>}
              {organizing && group && <div className="watchlist-group-actions">
                <button type="button" className="watchlist-icon" disabled={busy} onClick={() => openEditor(group)} aria-label={`Edit ${label}`} title={`Edit ${label}`}><MoreHorizontal size={20} /></button>
              </div>}
            </header>}
            <div id={`watchlist-group-${id}`} className="watchlist-group-rows" hidden={group?.collapsed}>
              {rows.map((snapshot) => (
                <div key={snapshot.ticker} data-watchlist-ticker={snapshot.ticker}
                  className={`watchlist-group-row${dropping && target?.ticker === snapshot.ticker ? target.after ? " watchlist-insert-after" : " watchlist-insert-before" : ""}${drag?.id === snapshot.ticker ? " watchlist-dragging" : ""}`}>
                  {organizing && grip(snapshot.ticker, snapshot.ticker)}
                  {renderRow(snapshot)}
                  {organizing && (
                    <button type="button" className="mobile-watchlist-bookmark saved" disabled={busy}
                      aria-label={`Remove ${snapshot.ticker} from Watchlist`} title="Remove from Watchlist"
                      onClick={() => void run(() => onRemove(snapshot.ticker), `${snapshot.ticker} removed from watchlist.`)}>
                      <BookmarkCheck size={21} aria-hidden="true" />
                    </button>
                  )}
                </div>
              ))}
              {rows.length === 0 && (
                <div className="watchlist-group-empty">
                  {matching.length > 0 ? <button type="button" onClick={() => onRevealGroup(id)}>Show {matching.length} symbol{matching.length === 1 ? "" : "s"}</button>
                    : total > 0 ? <span>No symbols match your filters.</span>
                      : <span>Use Organize to move stocks here.</span>}
                </div>
              )}
            </div>
          </section>
        );
      })}
      {drag?.active && <div className="watchlist-drag-preview" style={{ left: drag.x + 12, top: drag.y - 24 }} aria-hidden="true"><GripVertical size={14} />{drag.label}</div>}

      {editor && (
        <WatchlistDialog title={editor === "new" ? "New group" : "Edit group"} onClose={() => { if (!busy) { setEditor(null); setError(null); } }}>
          <form onSubmit={(event) => {
            event.preventDefault();
            if (!name.trim()) { setError("Enter a group name."); return; }
            void run(() => editorGroup
              ? actions.onUpdateWatchlistGroup(editorGroup.id, { name })
              : actions.onCreateWatchlistGroup({ name, color: WATCHLIST_COLORS[groups.length % WATCHLIST_COLORS.length].value }),
            `Group ${name.trim()} saved.`, true);
          }}>
            <label className="watchlist-name">Group name<input autoFocus value={name} onChange={(event) => setName(event.target.value)} maxLength={80} placeholder="e.g. Tech leaders" required disabled={busy} /></label>
            {error && <p className="watchlist-error" role="alert">{error}</p>}
            <button className="watchlist-primary" type="submit" disabled={busy || !name.trim()}>{busy ? "Saving…" : editorGroup ? "Save changes" : "Create group"}</button>
            {editorGroup && <div className="watchlist-delete-group"><button type="button" disabled={busy} onClick={() => void run(() => actions.onDeleteWatchlistGroup(editorGroup.id), `${editorGroup.name} deleted. Stocks remain in your watchlist.`, true)}><Trash2 size={16} />Delete group</button><p>Stocks will stay in your watchlist.</p></div>}
          </form>
        </WatchlistDialog>
      )}
      {movingTicker && (
        <WatchlistDialog title={`Move ${movingTicker}`} onClose={() => { if (!busy) { setMovingTicker(null); setError(null); } }}>
          <p className="watchlist-dialog-hint">Choose a group</p>
          <div className="watchlist-move-options">{sections.map((group) => {
            const id = group?.id ?? null;
            return <button type="button" key={id ?? "ungrouped"} disabled={busy || currentItem?.group_id === id} onClick={() => moveSymbol(id)}><span className="watchlist-group-dot" style={{ backgroundColor: group?.color ?? "#8b8e97" }} /><span>{group?.name ?? "Ungrouped"}</span>{currentItem?.group_id === id && <Check size={17} />}</button>;
          })}</div>
          <div className="watchlist-reorder-actions"><button type="button" disabled={busy || siblingIndex <= 0} onClick={() => moveSymbol(currentItem?.group_id ?? null, siblings[siblingIndex - 1]?.ticker)}><ArrowUp size={16} />Move up</button><button type="button" disabled={busy || siblingIndex >= siblings.length - 1} onClick={() => moveSymbol(currentItem?.group_id ?? null, siblings[siblingIndex + 2]?.ticker)}><ArrowDown size={16} />Move down</button></div>
          {error && <p className="watchlist-error" role="alert">{error}</p>}
          <button type="button" className="watchlist-remove" disabled={busy} onClick={() => void run(() => onRemove(movingTicker), `${movingTicker} removed from watchlist.`, true)}><Trash2 size={16} />Remove from watchlist</button>
        </WatchlistDialog>
      )}
    </div>
  );
}
