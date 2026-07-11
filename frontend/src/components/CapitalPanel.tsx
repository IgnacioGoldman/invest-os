import { memo, useMemo, useState, type ChangeEvent, type ReactNode } from "react";
import {
  ArrowRight,
  Bitcoin,
  Building2,
  Check,
  ChevronRight,
  FileSpreadsheet,
  FileText,
  KeyRound,
  Landmark,
  Pencil,
  Plus,
  Plug,
  RefreshCcw,
  Trash2,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import type {
  CashBalance,
  Holding,
  ManualCapitalEntryRequest,
  ManualCapitalSnapshot,
  PortfolioSnapshot,
  UserConnection,
  UserConnectionSource,
  UserConnectionUpdate,
} from "../api";

type Method = "connect" | "form" | "csv";
type ManualKind = "bank" | "cash" | "broker" | "crypto";

type Props = {
  manualCapital: ManualCapitalSnapshot | null;
  snapshot: PortfolioSnapshot | null;
  connections: UserConnection[];
  saving: boolean;
  status: string | null;
  connectionSaving: boolean;
  connectionStatus: string | null;
  onSaveManualEntry: (entry: ManualCapitalEntryRequest) => Promise<void>;
  onUpdateManualEntry: (entryId: string, entry: ManualCapitalEntryRequest) => Promise<void>;
  onDeleteManualEntry: (entryId: string, label: string) => Promise<void>;
  onConfigureConnection: (source: "ibkr" | "binance") => void;
  onSaveConnection: (source: UserConnectionSource, connection: UserConnectionUpdate) => Promise<void>;
  onDeleteConnection: (source: UserConnectionSource, label: string) => Promise<void>;
  onRefreshConnection: (source: UserConnectionSource) => Promise<void>;
};

type CapitalSource = {
  id: string;
  sourceType: "manual" | "connection";
  method: Method;
  kind: string;
  name: string;
  amount?: number | null;
  currency: string;
  note?: string | null;
  meta?: string;
  entry: Record<string, unknown>;
  connectionSource?: UserConnectionSource;
};

type Valuation = {
  amount: number | null;
  currency: string;
  meta?: string;
};

const CONNECT_OPTIONS: Array<{
  id: UserConnectionSource;
  name: string;
  kind: string;
  icon: LucideIcon;
  meta: string;
}> = [
  { id: "ibkr", name: "Interactive Brokers", kind: "Broker", icon: Building2, meta: "Positions, cash, orders, activity" },
  { id: "binance", name: "Binance", kind: "Crypto", icon: Bitcoin, meta: "Crypto balances, orders, ledger" },
];

const CONNECTION_PLATFORM_NAMES: Record<UserConnectionSource, string[]> = {
  ibkr: ["Interactive Brokers"],
  binance: ["Binance"],
};

const FORM_KINDS: Array<{ id: ManualKind; name: string; icon: LucideIcon }> = [
  { id: "bank", name: "Bank account", icon: Landmark },
  { id: "cash", name: "Cash / savings", icon: Wallet },
  { id: "broker", name: "Broker manual", icon: Building2 },
  { id: "crypto", name: "Crypto wallet", icon: Bitcoin },
];

const emptyManualForm = {
  kind: "bank" as ManualKind,
  label: "",
  platform: "",
  balance: "",
  currency: "EUR",
  note: "",
  symbol: "",
  quantity: "",
  estimatedPrice: "",
  assetClass: "",
};

type ManualForm = typeof emptyManualForm;

const optionalNumber = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const numeric = Number(trimmed);
  return Number.isFinite(numeric) ? numeric : null;
};

const optionalText = (value: string) => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

const money = (amount: number | null | undefined, currency: string) => {
  if (amount == null || !Number.isFinite(amount)) return currency;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "EUR",
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency || "EUR"} ${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
};

const rowString = (row: Record<string, unknown>, key: string, fallback = "") => {
  const value = row[key];
  return typeof value === "string" && value.trim() ? value : fallback;
};

const rowNumber = (row: Record<string, unknown>, key: string) => {
  const value = row[key];
  if (value == null || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const rowId = (row: Record<string, unknown>, fallback: string) => rowString(row, "id", fallback);

const sourceAmount = (row: Record<string, unknown>) => {
  const balance = rowNumber(row, "balance");
  if (balance != null) return balance;
  const quantity = rowNumber(row, "quantity");
  const price = rowNumber(row, "estimated_price");
  if (quantity != null && price != null) return quantity * price;
  const costBasis = rowNumber(row, "cost_basis");
  if (costBasis != null) return costBasis;
  return null;
};

const matchingCash = (row: Record<string, unknown>, cashBalances: CashBalance[]) => {
  const id = rowString(row, "id");
  const platform = rowString(row, "platform").toLowerCase();
  const account = rowString(row, "account_name").toLowerCase();
  return cashBalances.find((cash) => {
    if (cash.source !== "manual") return false;
    if (id && cash.id === id) return true;
    return cash.platform.toLowerCase() === platform && account !== "";
  }) ?? null;
};

const matchingHolding = (row: Record<string, unknown>, holdings: Holding[]) => {
  const id = rowString(row, "id");
  const platform = rowString(row, "platform").toLowerCase();
  const symbol = rowString(row, "symbol").toUpperCase();
  return holdings.find((holding) => {
    if (holding.source !== "manual") return false;
    if (id && holding.id === id) return true;
    return holding.platform.toLowerCase() === platform && holding.symbol.toUpperCase() === symbol;
  }) ?? null;
};

const valuationForRow = (
  row: Record<string, unknown>,
  snapshot: PortfolioSnapshot | null,
  fallbackCurrency: string,
): Valuation => {
  if (!snapshot) return { amount: sourceAmount(row), currency: fallbackCurrency };

  if (rowString(row, "kind") === "bank_cash" || rowNumber(row, "balance") != null) {
    const cash = matchingCash(row, snapshot.cash_balances);
    if (cash) {
      return {
        amount: cash.value_in_base ?? cash.balance,
        currency: cash.value_in_base != null ? snapshot.base_currency : cash.currency,
        meta: cash.value_in_base != null ? "Tracked in portfolio" : undefined,
      };
    }
  }

  const holding = matchingHolding(row, snapshot.holdings);
  if (holding && (holding.value_in_base != null || holding.market_value > 0)) {
    return {
      amount: holding.value_in_base ?? holding.market_value,
      currency: holding.value_in_base != null ? snapshot.base_currency : holding.currency,
      meta: holding.valuation_source ? `Valued from ${holding.valuation_source}` : "Tracked in portfolio",
    };
  }

  return { amount: sourceAmount(row), currency: fallbackCurrency };
};

const manualSourcesFromCapital = (
  manualCapital: ManualCapitalSnapshot | null,
  snapshot: PortfolioSnapshot | null,
): CapitalSource[] => {
  if (!manualCapital) return [];
  const cashSources = manualCapital.cash.map((row, index) => {
    const currency = rowString(row, "currency", "EUR");
    const valuation = valuationForRow(row, snapshot, currency);
    return {
      id: rowId(row, `cash-${index}`),
      sourceType: "manual" as const,
      method: "form" as Method,
      kind: rowString(row, "purpose", "Cash"),
      name: rowString(row, "account_name", rowString(row, "platform", "Cash account")),
      amount: valuation.amount,
      currency: valuation.currency,
      note: rowString(row, "notes"),
      meta: valuation.meta ?? rowString(row, "platform", "Manual cash"),
      entry: row,
    };
  });
  const assetSources = manualCapital.assets.map((row, index) => {
    const currency = rowString(row, "currency", "EUR");
    const valuation = valuationForRow(row, snapshot, currency);
    return {
      id: rowId(row, `asset-${index}`),
      sourceType: "manual" as const,
      method: "form" as Method,
      kind: rowString(row, "asset_class", "Asset"),
      name: rowString(row, "name", rowString(row, "symbol", "Manual asset")),
      amount: valuation.amount,
      currency: valuation.currency,
      note: rowString(row, "notes"),
      meta: valuation.meta ?? ([
        rowString(row, "platform"),
        rowString(row, "symbol"),
        rowNumber(row, "quantity") != null ? `${rowNumber(row, "quantity")} units` : "",
      ].filter(Boolean).join(" · ") || "Manual asset"),
      entry: row,
    };
  });
  return [...cashSources, ...assetSources];
};

const connectionValue = (
  source: UserConnectionSource,
  snapshot: PortfolioSnapshot | null,
) => {
  if (!snapshot) {
    return {
      amount: null,
      holdings: 0,
      cash: 0,
      currency: "EUR",
    };
  }
  const holdings = snapshot.holdings.filter((holding) => holding.source === source);
  const cashBalances = snapshot.cash_balances.filter((cash) => cash.source === source);
  const platformNames = CONNECTION_PLATFORM_NAMES[source];
  const platformValue = snapshot.platform_breakdown
    .filter((item) => platformNames.includes(item.name))
    .reduce((total, item) => total + item.value, 0);
  const holdingValue = holdings.reduce((total, holding) => {
    if (holding.value_in_base != null) return total + holding.value_in_base;
    if (holding.currency === snapshot.base_currency) return total + holding.market_value;
    return total;
  }, 0);
  const cashValue = cashBalances.reduce((total, cash) => {
    if (cash.value_in_base != null) return total + cash.value_in_base;
    if (cash.currency === snapshot.base_currency) return total + cash.balance;
    return total;
  }, 0);
  return {
    amount: platformValue || holdingValue + cashValue,
    holdings: holdings.length,
    cash: cashBalances.length,
    currency: snapshot.base_currency,
  };
};

const connectionSourcesFromSnapshot = (
  connections: UserConnection[],
  snapshot: PortfolioSnapshot | null,
): CapitalSource[] => {
  const bySource = new Map(connections.map((connection) => [connection.source, connection]));
  return CONNECT_OPTIONS.flatMap((option) => {
    const connection = bySource.get(option.id);
    const value = connectionValue(option.id, snapshot);
    const hasSnapshotRows = value.holdings > 0 || value.cash > 0;
    if (!connection?.configured && !hasSnapshotRows) return [];
    const pieces = [
      value.holdings ? `${value.holdings} holdings` : "",
      value.cash ? `${value.cash} cash balances` : "",
      connection?.configured ? "Connected" : "Cached data",
    ].filter(Boolean);
    return [{
      id: `connection-${option.id}`,
      sourceType: "connection" as const,
      method: "connect" as Method,
      kind: option.kind,
      name: connection?.label ?? option.name,
      amount: hasSnapshotRows ? value.amount : null,
      currency: value.currency,
      meta: pieces.join(" · "),
      entry: {},
      connectionSource: option.id,
    }];
  });
};

const sourcesFromCapital = (
  manualCapital: ManualCapitalSnapshot | null,
  snapshot: PortfolioSnapshot | null,
  connections: UserConnection[],
): CapitalSource[] => [
  ...connectionSourcesFromSnapshot(connections, snapshot),
  ...manualSourcesFromCapital(manualCapital, snapshot),
];

const connectionForSource = (
  connections: UserConnection[],
  source: UserConnectionSource,
): UserConnection => {
  const saved = connections.find((connection) => connection.source === source);
  if (saved) return saved;
  const option = CONNECT_OPTIONS.find((item) => item.id === source) ?? CONNECT_OPTIONS[0];
  return {
    source,
    label: option.name,
    configured: false,
  };
};

function sourceTotals(sources: CapitalSource[]) {
  const totals = new Map<string, number>();
  sources.forEach((source) => {
    if (source.amount == null) return;
    totals.set(source.currency, (totals.get(source.currency) ?? 0) + source.amount);
  });
  return [...totals.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amount]) => money(amount, currency));
}

export const CapitalPanel = memo(function CapitalPanel({
  manualCapital,
  snapshot,
  connections,
  saving,
  status,
  connectionSaving,
  connectionStatus,
  onSaveManualEntry,
  onUpdateManualEntry,
  onDeleteManualEntry,
  onConfigureConnection,
  onSaveConnection,
  onDeleteConnection,
  onRefreshConnection,
}: Props) {
  const [adding, setAdding] = useState(false);
  const [method, setMethod] = useState<Method | null>(null);
  const [editingSource, setEditingSource] = useState<CapitalSource | null>(null);
  const [editingConnection, setEditingConnection] = useState<UserConnectionSource | null>(null);
  const sources = useMemo(
    () => sourcesFromCapital(manualCapital, snapshot, connections),
    [connections, manualCapital, snapshot],
  );
  const totals = useMemo(() => sourceTotals(sources), [sources]);
  const activeConnectionEditor = editingConnection ? connectionForSource(connections, editingConnection) : null;

  const closeFlow = () => {
    setAdding(false);
    setMethod(null);
    setEditingSource(null);
  };

  const editSource = (source: CapitalSource) => {
    if (source.sourceType === "connection" && source.connectionSource) {
      setEditingConnection(source.connectionSource);
      return;
    }
    setEditingSource(source);
    setAdding(true);
    setMethod("form");
  };

  return (
    <div className="capital-shell">
      <header className="capital-hero">
        <div>
          <h2>Capital sources</h2>
          <p>Add everything you own. Connect a platform, type it in, or import a file.</p>
        </div>
        <div className="capital-total-card">
          <span>Tracked capital</span>
          <strong>{totals.length ? totals.join(" · ") : "No tracked capital"}</strong>
          <small>{sources.length} sources</small>
        </div>
      </header>

      {!adding && (
        <button type="button" className="capital-add-card" onClick={() => setAdding(true)}>
          <span className="capital-add-icon">
            <Plus size={20} strokeWidth={2.5} aria-hidden="true" />
          </span>
          <span>
            <strong>Add a capital source</strong>
            <small>Connect a broker, enter a balance manually, or upload trade history.</small>
          </span>
          <ChevronRight size={20} aria-hidden="true" />
        </button>
      )}

      {adding && method == null && (
        <section className="panel capital-flow-panel">
          <FlowHeading title="How do you want to add it?" onCancel={closeFlow} />
          <div className="capital-method-grid">
            <MethodCard
              icon={Plug}
              title="Connect"
              subtitle="Live sync with a broker or exchange"
              example="Interactive Brokers or Binance"
              onClick={() => setMethod("connect")}
            />
            <MethodCard
              icon={FileText}
              title="Form"
              subtitle="Enter a balance manually"
              example="Bank account, wallet, external asset"
              onClick={() => setMethod("form")}
            />
            <MethodCard
              icon={FileSpreadsheet}
              title="CSV"
              subtitle="Upload trades or holdings"
              example="Fallback when you do not want to connect"
              onClick={() => setMethod("csv")}
            />
          </div>
        </section>
      )}

      {adding && method === "connect" && (
        <ConnectFlow onCancel={() => setMethod(null)} onConfigureConnection={onConfigureConnection} />
      )}
      {adding && method === "form" && (
        <FormFlow
          editingSource={editingSource}
          saving={saving}
          status={status}
          onCancel={closeFlow}
          onAdd={async (entry) => {
            await onSaveManualEntry(entry);
            closeFlow();
          }}
          onUpdate={async (entryId, entry) => {
            await onUpdateManualEntry(entryId, entry);
            closeFlow();
          }}
        />
      )}
      {adding && method === "csv" && <CsvFlow onCancel={() => setMethod(null)} onConfigureConnection={onConfigureConnection} />}

      {activeConnectionEditor && (
        <ConnectionEditor
          connection={activeConnectionEditor}
          saving={connectionSaving}
          onCancel={() => setEditingConnection(null)}
          onSave={async (update) => {
            await onSaveConnection(activeConnectionEditor.source, update);
            setEditingConnection(null);
          }}
        />
      )}

      <section className="capital-sources-section">
        <div className="capital-section-heading">
          <h3>Your sources ({sources.length})</h3>
          {manualCapital && (
            <span>
              {connectionStatus ?? `${sources.filter((source) => source.sourceType === "connection").length} connections · ${manualCapital.cash.length} cash · ${manualCapital.assets.length} assets`}
            </span>
          )}
        </div>
        {sources.length === 0 ? (
          <div className="capital-empty-source">Nothing added yet. Tap the add card above to add your first source.</div>
        ) : (
          <div className="capital-source-list">
            {sources.map((source) => (
              <SourceRow
                key={source.id}
                source={source}
                refreshing={connectionSaving}
                onEdit={() => editSource(source)}
                onRefresh={source.connectionSource ? () => onRefreshConnection(source.connectionSource as UserConnectionSource) : undefined}
                onDelete={source.connectionSource
                  ? () => onDeleteConnection(source.connectionSource as UserConnectionSource, source.name)
                  : () => onDeleteManualEntry(source.id, source.name)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
});

function FlowHeading({ title, onCancel }: { title: string; onCancel: () => void }) {
  return (
    <div className="capital-flow-heading">
      <h3>{title}</h3>
      <button type="button" onClick={onCancel} title="Cancel">
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

function MethodCard({
  icon: Icon,
  title,
  subtitle,
  example,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  example: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className="capital-method-card" onClick={onClick}>
      <span className="capital-method-icon">
        <Icon size={20} aria-hidden="true" />
      </span>
      <strong>{title}</strong>
      <span>{subtitle}</span>
      <em>{example}</em>
    </button>
  );
}

function FlowShell({ title, onCancel, children }: { title: string; onCancel: () => void; children: ReactNode }) {
  return (
    <section className="panel capital-flow-panel">
      <FlowHeading title={title} onCancel={onCancel} />
      <div className="capital-flow-body">{children}</div>
    </section>
  );
}

function ConnectFlow({
  onCancel,
  onConfigureConnection,
}: {
  onCancel: () => void;
  onConfigureConnection: (source: "ibkr" | "binance") => void;
}) {
  return (
    <FlowShell title="Connect a platform" onCancel={onCancel}>
      <div className="capital-connect-grid">
        {CONNECT_OPTIONS.map((option) => {
          const Icon = option.icon;
          return (
            <button
              type="button"
              className="capital-connect-option"
              key={option.id}
              onClick={() => onConfigureConnection(option.id)}
            >
              <span className="capital-method-icon">
                <Icon size={18} aria-hidden="true" />
              </span>
              <span>
                <strong>{option.name}</strong>
                <small>{option.kind} · {option.meta}</small>
              </span>
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </FlowShell>
  );
}

function formFromSource(source: CapitalSource | null): ManualForm {
  if (!source) return emptyManualForm;
  const row = source.entry;
  const isCash = rowString(row, "kind") === "bank_cash" || rowNumber(row, "balance") != null;
  if (isCash) {
    return {
      ...emptyManualForm,
      kind: rowString(row, "purpose") === "deployable_cash" ? "cash" : "bank",
      label: rowString(row, "account_name", source.name),
      platform: rowString(row, "platform", "Bank"),
      balance: rowNumber(row, "balance")?.toString() ?? "",
      currency: rowString(row, "currency", source.currency),
      note: rowString(row, "notes"),
    };
  }

  const assetClass = rowString(row, "asset_class", "manual");
  return {
    ...emptyManualForm,
    kind: assetClass === "crypto" ? "crypto" : "broker",
    label: rowString(row, "name", source.name),
    platform: rowString(row, "platform", "Broker manual"),
    currency: rowString(row, "currency", source.currency),
    note: rowString(row, "notes"),
    symbol: rowString(row, "symbol"),
    quantity: rowNumber(row, "quantity")?.toString() ?? "",
    estimatedPrice: rowNumber(row, "estimated_price")?.toString() ?? "",
    assetClass,
  };
}

function FormFlow({
  editingSource,
  saving,
  status,
  onCancel,
  onAdd,
  onUpdate,
}: {
  editingSource: CapitalSource | null;
  saving: boolean;
  status: string | null;
  onCancel: () => void;
  onAdd: (entry: ManualCapitalEntryRequest) => Promise<void>;
  onUpdate: (entryId: string, entry: ManualCapitalEntryRequest) => Promise<void>;
}) {
  const [form, setForm] = useState<ManualForm>(() => formFromSource(editingSource));
  const kindMeta = FORM_KINDS.find((kind) => kind.id === form.kind) ?? FORM_KINDS[0];
  const isCashLike = form.kind === "bank" || form.kind === "cash";
  const balance = optionalNumber(form.balance);
  const quantity = optionalNumber(form.quantity);
  const canSave = isCashLike
    ? form.label.trim() !== "" && balance != null
    : form.label.trim() !== "" && form.symbol.trim() !== "" && quantity != null;

  const updateForm = (key: keyof ManualForm, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const save = async () => {
    if (!canSave) return;
    const entry = formToEntry(form, kindMeta.name, editingSource?.entry);
    if (editingSource) {
      await onUpdate(editingSource.id, entry);
      return;
    }
    await onAdd(entry);
  };

  return (
    <FlowShell title={editingSource ? "Edit capital source" : "Enter a balance manually"} onCancel={onCancel}>
      <div className="capital-kind-grid">
        {FORM_KINDS.map((kind) => {
          const Icon = kind.icon;
          const active = kind.id === form.kind;
          return (
            <button
              type="button"
              className={`capital-kind-card ${active ? "active" : ""}`}
              key={kind.id}
              onClick={() => updateForm("kind", kind.id)}
              aria-pressed={active}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{kind.name}</span>
            </button>
          );
        })}
      </div>

      <div className="capital-flow-grid">
        <TextField
          label="Label"
          value={form.label}
          onChange={(value) => updateForm("label", value)}
          placeholder={`e.g. ${kindMeta.name}`}
        />
        <TextField
          label="Platform"
          value={form.platform}
          onChange={(value) => updateForm("platform", value)}
          placeholder={kindMeta.name}
        />
        <TextField label="Currency" value={form.currency} onChange={(value) => updateForm("currency", value.toUpperCase())} />

        {isCashLike ? (
          <NumberField
            label="Balance"
            value={form.balance}
            onChange={(value) => updateForm("balance", value)}
            placeholder="10000"
          />
        ) : (
          <>
            <TextField
              label="Symbol"
              value={form.symbol}
              onChange={(value) => updateForm("symbol", value.toUpperCase())}
              placeholder={form.kind === "crypto" ? "BTC" : "DT"}
            />
            <NumberField
              label="Quantity"
              value={form.quantity}
              onChange={(value) => updateForm("quantity", value)}
              placeholder="10"
            />
            <NumberField
              label="Est. price"
              value={form.estimatedPrice}
              onChange={(value) => updateForm("estimatedPrice", value)}
              placeholder="Optional"
            />
            <TextField
              label="Asset class"
              value={form.assetClass}
              onChange={(value) => updateForm("assetClass", value.toLowerCase())}
              placeholder={form.kind === "crypto" ? "crypto" : "rsu"}
            />
          </>
        )}

        <TextField
          label="Note"
          value={form.note}
          onChange={(value) => updateForm("note", value)}
          placeholder="Emergency fund"
        />
      </div>

      <div className="capital-flow-actions">
        {status && <span>{status}</span>}
        <button type="button" className="capital-secondary-button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" onClick={save} disabled={!canSave || saving}>
          {saving ? "Saving" : editingSource ? "Update source" : "Add source"}
          {!saving && <Check size={15} aria-hidden="true" />}
        </button>
      </div>
    </FlowShell>
  );
}

function CsvFlow({
  onCancel,
  onConfigureConnection,
}: {
  onCancel: () => void;
  onConfigureConnection: (source: "ibkr" | "binance") => void;
}) {
  const [fileName, setFileName] = useState("");

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setFileName(file?.name ?? "");
  };

  return (
    <FlowShell title="Upload a CSV of trades or holdings" onCancel={onCancel}>
      <label className="capital-csv-dropzone">
        <FileSpreadsheet size={24} aria-hidden="true" />
        <strong>{fileName || "Drop your CSV or click to browse"}</strong>
        <span>Fallback for broker exports. Current import setup continues in Settings.</span>
        <input type="file" accept=".csv,text/csv" onChange={selectFile} />
      </label>
      <div className="capital-flow-actions">
        <button type="button" className="capital-secondary-button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" onClick={() => onConfigureConnection("ibkr")}>
          Continue
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </div>
    </FlowShell>
  );
}

function formToEntry(
  form: ManualForm,
  kindName: string,
  existing?: Record<string, unknown>,
): ManualCapitalEntryRequest {
  const currency = form.currency.trim().toUpperCase() || "EUR";
  const notes = optionalText(form.note);
  const platform = form.platform.trim() || kindName;
  if (form.kind === "bank" || form.kind === "cash") {
    return {
      kind: "bank_cash",
      platform,
      account_name: form.label.trim(),
      currency,
      balance: optionalNumber(form.balance),
      purpose: form.kind === "cash" ? "deployable_cash" : "other",
      notes,
    };
  }

  const assetClass = form.kind === "crypto" ? "crypto" : optionalText(form.assetClass) ?? "manual";
  const assetKind = ["stock", "equity", "etf"].includes(assetClass) ? "stock" : "other_asset";
  return {
    kind: assetKind,
    platform,
    currency,
    symbol: form.symbol.trim().toUpperCase(),
    name: form.label.trim(),
    asset_class: assetClass,
    quantity: optionalNumber(form.quantity),
    estimated_price: optionalNumber(form.estimatedPrice),
    cost_basis: existing ? rowNumber(existing, "cost_basis") : null,
    sector: existing ? optionalText(rowString(existing, "sector")) : null,
    vertical: existing ? optionalText(rowString(existing, "vertical")) : null,
    geography: existing ? optionalText(rowString(existing, "geography")) : null,
    notes,
  };
}

function SourceRow({
  source,
  refreshing,
  onEdit,
  onRefresh,
  onDelete,
}: {
  source: CapitalSource;
  refreshing: boolean;
  onEdit: () => void;
  onRefresh?: () => void;
  onDelete: () => void;
}) {
  return (
    <article
      className="capital-source-row"
      role="button"
      tabIndex={0}
      onClick={onEdit}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onEdit();
        }
      }}
    >
      <span className="capital-source-icon">
        {source.method === "connect" && <Plug size={17} aria-hidden="true" />}
        {source.method === "form" && <FileText size={17} aria-hidden="true" />}
        {source.method === "csv" && <FileSpreadsheet size={17} aria-hidden="true" />}
      </span>
      <div>
        <h4>{source.name}</h4>
        <span>{source.meta ?? source.note ?? methodLabel(source.method)}</span>
      </div>
      <em>{source.kind}</em>
      <strong>{money(source.amount, source.currency)}</strong>
      <span className="capital-source-actions">
        <button
          type="button"
          className="capital-icon-action"
          onClick={(event) => {
            event.stopPropagation();
            onEdit();
          }}
          title={`Edit ${source.name}`}
        >
          <Pencil size={15} aria-hidden="true" />
        </button>
        {onRefresh && (
          <button
            type="button"
            className="capital-icon-action"
            onClick={(event) => {
              event.stopPropagation();
              onRefresh();
            }}
            disabled={refreshing}
            title={`Refresh ${source.name}`}
          >
            <RefreshCcw size={15} aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          className="capital-icon-action danger"
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          title={`Delete ${source.name}`}
        >
          <Trash2 size={15} aria-hidden="true" />
        </button>
      </span>
    </article>
  );
}

function ConnectionEditor({
  connection,
  saving,
  onCancel,
  onSave,
}: {
  connection: UserConnection;
  saving: boolean;
  onCancel: () => void;
  onSave: (update: UserConnectionUpdate) => Promise<void>;
}) {
  const [form, setForm] = useState(() => ({
    ibkr_host: connection.ibkr_host ?? "127.0.0.1",
    ibkr_port: String(connection.ibkr_port ?? 7497),
    ibkr_client_id: String(connection.ibkr_client_id ?? 1),
    ibkr_flex_query_id: connection.ibkr_flex_query_id ?? "1554875",
    ibkr_flex_token: "",
    binance_api_key: "",
    binance_api_secret: "",
    binance_ledger_start_date: connection.binance_ledger_start_date ?? "",
  }));

  const updateForm = (key: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const save = async () => {
    if (connection.source === "ibkr") {
      await onSave({
        ibkr_host: form.ibkr_host,
        ibkr_port: optionalNumber(form.ibkr_port),
        ibkr_client_id: optionalNumber(form.ibkr_client_id),
        ibkr_flex_query_id: form.ibkr_flex_query_id,
        ...(form.ibkr_flex_token.trim() ? { ibkr_flex_token: form.ibkr_flex_token } : {}),
      });
      return;
    }
    await onSave({
      ...(form.binance_api_key.trim() ? { binance_api_key: form.binance_api_key } : {}),
      ...(form.binance_api_secret.trim() ? { binance_api_secret: form.binance_api_secret } : {}),
      binance_ledger_start_date: form.binance_ledger_start_date || null,
    });
  };

  return (
    <section className="panel capital-flow-panel">
      <FlowHeading title={`Edit ${connection.label}`} onCancel={onCancel} />
      <div className="capital-flow-body">
        <div className="capital-connection-editor-note">
          <KeyRound size={16} aria-hidden="true" />
          <span>Saved secrets stay local and are shown masked. Leave a secret field blank to keep the saved value.</span>
        </div>
        <div className="capital-flow-grid">
          {connection.source === "ibkr" ? (
            <>
              <TextField label="Host" value={form.ibkr_host} onChange={(value) => updateForm("ibkr_host", value)} />
              <NumberField label="Port" value={form.ibkr_port} onChange={(value) => updateForm("ibkr_port", value)} />
              <NumberField label="Client ID" value={form.ibkr_client_id} onChange={(value) => updateForm("ibkr_client_id", value)} />
              <TextField
                label="Flex query ID"
                value={form.ibkr_flex_query_id}
                onChange={(value) => updateForm("ibkr_flex_query_id", value)}
              />
              <TextField
                label="Flex token"
                value={form.ibkr_flex_token}
                onChange={(value) => updateForm("ibkr_flex_token", value)}
                placeholder={connection.ibkr_flex_token_preview ?? "Paste token"}
              />
            </>
          ) : (
            <>
              <TextField
                label="API key"
                value={form.binance_api_key}
                onChange={(value) => updateForm("binance_api_key", value)}
                placeholder={connection.binance_api_key_preview ?? "Paste API key"}
              />
              <TextField
                label="API secret"
                value={form.binance_api_secret}
                onChange={(value) => updateForm("binance_api_secret", value)}
                placeholder={connection.binance_api_secret_preview ?? "Paste API secret"}
              />
              <TextField
                label="Ledger start"
                value={form.binance_ledger_start_date}
                onChange={(value) => updateForm("binance_ledger_start_date", value)}
                placeholder="2025-08-18T15:07:00+00:00"
              />
            </>
          )}
        </div>
        <div className="capital-flow-actions">
          <button type="button" className="capital-secondary-button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" onClick={save} disabled={saving}>
            {saving ? "Saving" : "Save connection"}
            {!saving && <Check size={15} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </section>
  );
}

function methodLabel(method: Method) {
  if (method === "connect") return "Connected";
  if (method === "csv") return "CSV import";
  return "Manual entry";
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="capital-inline-field">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="capital-inline-field">
      <span>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}
