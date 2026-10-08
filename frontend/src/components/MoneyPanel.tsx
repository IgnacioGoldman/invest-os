import { Pencil, Plus, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  deleteMoneyEntry, fetchMoneyEntries, fetchMoneyExchangeRates, formatMoney,
  MONEY_CURRENCIES, moneyTotals, parseMoneyAmount, saveMoneyEntry,
  type ExchangeRates, type MoneyCurrency, type MoneyEntry, type MoneyStatus,
} from "../money";

export function MoneyPanel({ userId }: { userId: string }) {
  const [entries, setEntries] = useState<MoneyEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState<MoneyCurrency>("EUR");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState<MoneyStatus>("invested");
  const [displayCurrency, setDisplayCurrency] = useState<MoneyCurrency>("EUR");
  const [rates, setRates] = useState<ExchangeRates | null>(null);
  const [ratesLoading, setRatesLoading] = useState(false);
  const [ratesError, setRatesError] = useState(false);
  const mounted = useRef(false);
  const mutating = useRef(false);
  const revision = useRef(0);
  const addButton = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    if (mutating.current) return;
    const version = ++revision.current;
    try {
      const rows = await fetchMoneyEntries(userId);
      if (!mounted.current || version !== revision.current) return;
      setEntries(rows);
      setLoadError(null);
    } catch {
      if (mounted.current && version === revision.current) setLoadError("Could not load your amounts. Please try again.");
    } finally {
      if (mounted.current && version === revision.current) setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    mounted.current = true;
    void load();
    const refresh = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", refresh);
    return () => {
      mounted.current = false;
      revision.current++;
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  const loadRates = useCallback(async () => {
    setRatesLoading(true);
    setRatesError(false);
    try {
      const nextRates = await fetchMoneyExchangeRates();
      if (mounted.current) setRates(nextRates);
    } catch {
      if (mounted.current) setRatesError(true);
    } finally {
      if (mounted.current) setRatesLoading(false);
    }
  }, []);

  const needsConversion = entries.some((entry) => entry.currency !== displayCurrency);
  useEffect(() => {
    if (needsConversion) void loadRates();
  }, [needsConversion, loadRates]);

  const openForm = (entry?: MoneyEntry) => {
    setEditingId(entry?.id ?? null);
    setAmount(entry ? String(entry.amount) : "");
    setCurrency(entry?.currency ?? displayCurrency);
    setSource(entry?.source ?? "");
    setStatus(entry?.status ?? "invested");
    setError(null);
    setDeletingId(null);
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditingId(null);
    setError(null);
    requestAnimationFrame(() => addButton.current?.focus());
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (mutating.current) return;
    const parsed = parseMoneyAmount(amount);
    if (parsed === null) {
      setError("Enter an amount with up to two decimal places, e.g. 15000 or 15000,50.");
      return;
    }
    if (!source.trim()) {
      setError("Enter a source, e.g. Binance or Handelsbanken.");
      return;
    }
    mutating.current = true;
    revision.current++;
    setBusy(true);
    setError(null);
    try {
      const saved = await saveMoneyEntry(userId, { amount: parsed, currency, source, status }, editingId ?? undefined);
      if (!mounted.current) return;
      setEntries((current) => editingId ? current.map((entry) => entry.id === saved.id ? saved : entry) : [...current, saved]);
      closeForm();
    } catch {
      if (mounted.current) setError("Could not save this amount. Your changes are still here; please try again.");
    } finally {
      mutating.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (mutating.current) return;
    mutating.current = true;
    revision.current++;
    setBusy(true);
    setError(null);
    try {
      await deleteMoneyEntry(userId, id);
      if (!mounted.current) return;
      setEntries((current) => current.filter((entry) => entry.id !== id));
      setDeletingId(null);
      if (editingId === id) closeForm();
    } catch {
      if (mounted.current) setError("Could not delete this amount. Please try again.");
    } finally {
      mutating.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const totals = moneyTotals(entries, displayCurrency, rates);
  const investedPercent = totals && totals.total > 0 ? totals.invested / totals.total * 100 : 0;
  const percentage = (value: number) => `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}%`;

  return (
    <section className="money-panel" id="space-money" role="tabpanel" aria-labelledby="space-money-tab">
      {loading ? <p className="money-hint" role="status">Loading your amounts…</p> : loadError ? (
        <div className="money-load-error" role="alert">
          <p>{loadError}</p><button type="button" onClick={() => { setLoading(true); void load(); }}>Try again</button>
        </div>
      ) : (
        <>
          {!formOpen ? (
            <button type="button" className="money-add" ref={addButton} onClick={() => openForm()}>
              <Plus size={24} />Add amount
            </button>
          ) : (
            <form className="money-form" onSubmit={(event) => void submit(event)}>
              <header><h2>{editingId ? "Edit amount" : "Add amount"}</h2>
                <button type="button" className="money-icon" onClick={closeForm} disabled={busy} aria-label="Cancel amount"><X size={20} /></button>
              </header>
              <fieldset disabled={busy}>
                <div className="money-input-row">
                  <label>Amount<input autoFocus required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="15000" autoComplete="off" /></label>
                  <label>Currency<select value={currency} onChange={(event) => setCurrency(event.target.value as MoneyCurrency)}>
                    {MONEY_CURRENCIES.map((code) => <option key={code}>{code}</option>)}
                  </select></label>
                </div>
                <label>Source<input required maxLength={80} value={source} onChange={(event) => setSource(event.target.value)} placeholder="e.g. Binance, IBKR, Handelsbanken" /></label>
                <div className="money-status-choice" role="group" aria-label="Investment status">
                  {(["invested", "uninvested"] as const).map((choice) => (
                    <button type="button" key={choice} aria-pressed={status === choice} onClick={() => setStatus(choice)}>{choice === "invested" ? "Invested" : "Uninvested"}</button>
                  ))}
                </div>
                {error && <p className="money-error" role="alert">{error}</p>}
                <button type="submit" className="money-save">{busy ? "Saving…" : "Save amount"}</button>
              </fieldset>
            </form>
          )}
          {entries.length === 0 && !formOpen && <p className="money-hint">e.g. 15000 EUR · Binance, or 450000 SEK · Uninvested</p>}
          {!formOpen && error && <p className="money-error" role="alert">{error}</p>}
          {entries.length > 0 && (
            <ul className="money-list" aria-label="Your amounts">
              {entries.map((entry) => (
                <li key={entry.id}>
                  <div className="money-entry-info"><strong>{formatMoney(entry.amount, entry.currency)}</strong>
                    <span>{entry.source} · {entry.status === "invested" ? "Invested" : "Uninvested"}</span>
                  </div>
                  <div className="money-entry-actions">
                    {deletingId === entry.id ? (
                      <><button type="button" className="money-delete-confirm" disabled={busy} onClick={() => void remove(entry.id)}>{busy ? "Deleting…" : "Delete?"}</button>
                        <button type="button" className="money-icon" disabled={busy} onClick={() => { setDeletingId(null); setError(null); }} aria-label="Cancel deletion"><X size={18} /></button></>
                    ) : (
                      <><button type="button" className="money-icon" disabled={busy} onClick={() => openForm(entry)} aria-label={`Edit ${entry.source} ${entry.status} amount`}><Pencil size={18} /></button>
                        <button type="button" className="money-icon" disabled={busy} onClick={() => { setDeletingId(entry.id); setError(null); }} aria-label={`Delete ${entry.source} ${entry.status} amount`}><Trash2 size={18} /></button></>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {entries.length > 0 && (
            <section className="money-summary" aria-label="Invested and uninvested money">
              <header><h2>Your money</h2><label className="money-display-currency">Show in
                <select value={displayCurrency} onChange={(event) => setDisplayCurrency(event.target.value as MoneyCurrency)}>
                  {MONEY_CURRENCIES.map((code) => <option key={code}>{code}</option>)}
                </select>
              </label></header>
              {totals ? (
                <>
                  <strong className="money-total">{formatMoney(totals.total, displayCurrency)}</strong>
                  <div className="money-chart-layout">
                    <div className={`money-pie ${totals.total === 0 ? "empty" : ""}`} role="img"
                      aria-label={totals.total === 0 ? "No balance to show" : `Invested ${percentage(investedPercent)}, uninvested ${percentage(100 - investedPercent)}`}
                      style={{ background: totals.total > 0 ? `conic-gradient(var(--mobile-blue) 0% ${investedPercent}%, #55565d ${investedPercent}% 100%)` : undefined }} />
                    <dl className="money-legend">
                      <div><dt><i className="invested" />Invested <span>{percentage(investedPercent)}</span></dt><dd>{formatMoney(totals.invested, displayCurrency)}</dd></div>
                      <div><dt><i className="uninvested" />Uninvested <span>{percentage(totals.total > 0 ? 100 - investedPercent : 0)}</span></dt><dd>{formatMoney(totals.uninvested, displayCurrency)}</dd></div>
                    </dl>
                  </div>
                  {needsConversion && rates && <p className="money-rates-note">Converted using <a href="https://frankfurter.dev/" target="_blank" rel="noreferrer">ECB rates</a> · {rates.date}</p>}
                </>
              ) : (
                <p className="money-hint" role="status">{ratesLoading ? "Getting exchange rates…" : "The total needs exchange rates."}</p>
              )}
              {needsConversion && ratesError && <p className="money-error" role="alert">Could not refresh exchange rates. <button type="button" disabled={ratesLoading} onClick={() => void loadRates()}>Retry</button></p>}
            </section>
          )}
        </>
      )}
    </section>
  );
}
