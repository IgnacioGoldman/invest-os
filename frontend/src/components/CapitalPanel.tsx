import { memo, useMemo, useState } from "react";
import { ArrowRight, Landmark, PlugZap, Upload } from "lucide-react";
import type { ManualCapitalEntryKind, ManualCapitalEntryRequest, ManualCapitalSnapshot } from "../api";

type CapitalMode = "manual" | "connected" | "import";

type Props = {
  manualCapital: ManualCapitalSnapshot | null;
  saving: boolean;
  status: string | null;
  onSaveManualEntry: (entry: ManualCapitalEntryRequest) => Promise<void>;
  onConfigureConnection: (source: "ibkr" | "binance") => void;
};

const CAPITAL_MODES: Array<{
  id: CapitalMode;
  title: string;
  label: string;
  icon: typeof Landmark;
  recommended?: boolean;
}> = [
  { id: "manual", title: "Manual", label: "YAML", icon: Landmark },
  { id: "connected", title: "Connected", label: "Recommended", icon: PlugZap, recommended: true },
  { id: "import", title: "Import", label: "CSV / file", icon: Upload },
];

const emptyForm = {
  kind: "bank_cash" as ManualCapitalEntryKind,
  platform: "Bank",
  account_name: "",
  currency: "EUR",
  balance: "",
  purpose: "deployable_cash",
  symbol: "",
  name: "",
  asset_class: "stock",
  quantity: "",
  estimated_price: "",
  cost_basis: "",
  sector: "",
  vertical: "",
  geography: "",
  notes: "",
};

type ManualForm = typeof emptyForm;

const optionalNumber = (value: string) => (value.trim() === "" ? null : Number(value));
const optionalText = (value: string) => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

export const CapitalPanel = memo(function CapitalPanel({
  manualCapital,
  saving,
  status,
  onSaveManualEntry,
  onConfigureConnection,
}: Props) {
  const [mode, setMode] = useState<CapitalMode>("connected");
  const [form, setForm] = useState<ManualForm>(emptyForm);
  const isCash = form.kind === "bank_cash";
  const canSave = useMemo(() => {
    if (isCash) {
      return form.platform.trim() !== "" && optionalNumber(form.balance) != null;
    }
    return form.platform.trim() !== "" && form.symbol.trim() !== "" && optionalNumber(form.quantity) != null;
  }, [form, isCash]);

  const updateForm = (key: keyof ManualForm, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveManualEntry = async () => {
    if (!canSave) return;
    const entry: ManualCapitalEntryRequest = isCash
      ? {
          kind: "bank_cash",
          platform: form.platform,
          account_name: optionalText(form.account_name),
          currency: form.currency,
          balance: optionalNumber(form.balance),
          purpose: optionalText(form.purpose),
          notes: optionalText(form.notes),
        }
      : {
          kind: form.kind,
          platform: form.platform,
          currency: form.currency,
          symbol: optionalText(form.symbol),
          name: optionalText(form.name),
          asset_class: optionalText(form.asset_class),
          quantity: optionalNumber(form.quantity),
          estimated_price: optionalNumber(form.estimated_price),
          cost_basis: optionalNumber(form.cost_basis),
          sector: optionalText(form.sector),
          vertical: optionalText(form.vertical),
          geography: optionalText(form.geography),
          notes: optionalText(form.notes),
        };
    await onSaveManualEntry(entry);
    setForm((current) => ({
      ...emptyForm,
      kind: current.kind,
      platform: current.platform,
      currency: current.currency,
      purpose: current.purpose,
      asset_class: current.asset_class,
    }));
  };

  return (
    <section className="panel capital-panel">
      <div className="panel-heading">
        <h2>Capital</h2>
        <div className="panel-heading-actions">
          <span>{manualCapital ? `${manualCapital.cash.length + manualCapital.assets.length} manual` : "Manual"}</span>
        </div>
      </div>

      <div className="capital-mode-grid" role="list" aria-label="Capital input mode">
        {CAPITAL_MODES.map((item) => {
          const Icon = item.icon;
          const active = mode === item.id;
          return (
            <button
              type="button"
              key={item.id}
              className={`capital-mode-card ${active ? "active" : ""}`}
              onClick={() => setMode(item.id)}
              aria-pressed={active}
            >
              <Icon size={18} aria-hidden="true" />
              <span>
                <strong>{item.title}</strong>
                <small>{item.label}</small>
              </span>
            </button>
          );
        })}
      </div>

      {mode === "manual" && (
        <div className="capital-manual-grid">
          <label className="capital-field">
            <span>Entry type</span>
            <select value={form.kind} onChange={(event) => updateForm("kind", event.target.value)}>
              <option value="bank_cash">Bank cash</option>
              <option value="stock">Stock</option>
              <option value="other_asset">Other asset</option>
            </select>
          </label>
          <label className="capital-field">
            <span>Platform</span>
            <input value={form.platform} onChange={(event) => updateForm("platform", event.target.value)} />
          </label>
          <label className="capital-field">
            <span>Currency</span>
            <input value={form.currency} onChange={(event) => updateForm("currency", event.target.value.toUpperCase())} />
          </label>

          {isCash ? (
            <>
              <label className="capital-field">
                <span>Account</span>
                <input value={form.account_name} onChange={(event) => updateForm("account_name", event.target.value)} />
              </label>
              <label className="capital-field">
                <span>Balance</span>
                <input type="number" value={form.balance} onChange={(event) => updateForm("balance", event.target.value)} />
              </label>
              <label className="capital-field">
                <span>Purpose</span>
                <select value={form.purpose} onChange={(event) => updateForm("purpose", event.target.value)}>
                  <option value="deployable_cash">Deployable cash</option>
                  <option value="emergency_fund">Emergency fund</option>
                  <option value="monthly_spending">Monthly spending</option>
                  <option value="reserved_for_orders">Reserved for orders</option>
                  <option value="other">Other</option>
                </select>
              </label>
            </>
          ) : (
            <>
              <label className="capital-field">
                <span>Symbol</span>
                <input value={form.symbol} onChange={(event) => updateForm("symbol", event.target.value.toUpperCase())} />
              </label>
              <label className="capital-field">
                <span>Name</span>
                <input value={form.name} onChange={(event) => updateForm("name", event.target.value)} />
              </label>
              <label className="capital-field">
                <span>Asset class</span>
                <select value={form.asset_class} onChange={(event) => updateForm("asset_class", event.target.value)}>
                  <option value="stock">Stock</option>
                  <option value="etf">ETF</option>
                  <option value="rsu">RSU</option>
                  <option value="crypto">Crypto</option>
                  <option value="commodity">Commodity</option>
                  <option value="manual">Other</option>
                </select>
              </label>
              <label className="capital-field">
                <span>Quantity</span>
                <input type="number" value={form.quantity} onChange={(event) => updateForm("quantity", event.target.value)} />
              </label>
              <label className="capital-field">
                <span>Est. price</span>
                <input type="number" value={form.estimated_price} onChange={(event) => updateForm("estimated_price", event.target.value)} />
              </label>
              <label className="capital-field">
                <span>Cost basis</span>
                <input type="number" value={form.cost_basis} onChange={(event) => updateForm("cost_basis", event.target.value)} />
              </label>
            </>
          )}

          <label className="capital-field capital-field-wide">
            <span>Notes</span>
            <input value={form.notes} onChange={(event) => updateForm("notes", event.target.value)} />
          </label>
          <div className="capital-actions">
            {status && <span>{status}</span>}
            <button type="button" onClick={saveManualEntry} disabled={!canSave || saving}>
              {saving ? "Saving" : "Save manual entry"}
              {!saving && <ArrowRight size={16} aria-hidden="true" />}
            </button>
          </div>
        </div>
      )}

      {mode === "connected" && (
        <div className="capital-setup-grid">
          <button type="button" className="capital-setup-card" onClick={() => onConfigureConnection("ibkr")}>
            <strong>IBKR</strong>
            <span>Positions, cash, orders, activity</span>
            <ArrowRight size={16} aria-hidden="true" />
          </button>
          <button type="button" className="capital-setup-card" onClick={() => onConfigureConnection("binance")}>
            <strong>Binance</strong>
            <span>Crypto balances, orders, ledger</span>
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      {mode === "import" && (
        <div className="capital-import-panel">
          <Upload size={18} aria-hidden="true" />
          <span>CSV, broker export, or transaction file</span>
          <button type="button" onClick={() => onConfigureConnection("ibkr")}>
            Continue
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      )}
    </section>
  );
});
