import { memo, useEffect, useMemo, useState } from "react";
import { Gauge, Pencil, Save, ShieldCheck, SlidersHorizontal } from "lucide-react";

export type InvestorPersonalityId = "low_risk" | "high_risk" | "custom";
export type InvestorAllocationKey = "vwce" | "cashBonds" | "individualStocks" | "crypto";
export type InvestorAllocation = Record<InvestorAllocationKey, number>;

type Props = {
  personality: InvestorPersonalityId;
  customAllocation: InvestorAllocation;
  onPersonalityChange: (personality: InvestorPersonalityId) => void;
  onCustomAllocationChange: (key: InvestorAllocationKey, value: number) => void;
  onCustomAllocationBalance: () => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  canSave: boolean;
  savedAt?: string | null;
};

export const LOW_RISK_ALLOCATION: InvestorAllocation = {
  vwce: 70,
  cashBonds: 20,
  individualStocks: 10,
  crypto: 0,
};

export const HIGH_RISK_ALLOCATION: InvestorAllocation = {
  vwce: 50,
  cashBonds: 10,
  individualStocks: 25,
  crypto: 15,
};

export const DEFAULT_CUSTOM_ALLOCATION: InvestorAllocation = {
  vwce: 60,
  cashBonds: 20,
  individualStocks: 15,
  crypto: 5,
};

export const DEFAULT_INVESTOR_PERSONALITY: InvestorPersonalityId = "low_risk";

const PERSONALITY_OPTIONS = [
  {
    id: "low_risk",
    title: "Low Risk",
    caption: "Index core, cash buffer",
    icon: ShieldCheck,
  },
  {
    id: "high_risk",
    title: "High Risk",
    caption: "More stock and crypto risk",
    icon: Gauge,
  },
  {
    id: "custom",
    title: "Custom",
    caption: "Set your own target",
    icon: SlidersHorizontal,
  },
] as const;

const ALLOCATION_ROWS: Array<{ key: InvestorAllocationKey; label: string; highRiskLabel?: string }> = [
  { key: "vwce", label: "VWCE" },
  { key: "cashBonds", label: "Cash/bonds", highRiskLabel: "Cash" },
  { key: "individualStocks", label: "Individual stocks" },
  { key: "crypto", label: "Crypto" },
];

export function allocationForPersonality(
  personality: InvestorPersonalityId,
  customAllocation: InvestorAllocation,
): InvestorAllocation {
  if (personality === "low_risk") return LOW_RISK_ALLOCATION;
  if (personality === "high_risk") return HIGH_RISK_ALLOCATION;
  return customAllocation;
}

const allocationTotal = (allocation: InvestorAllocation) =>
  Object.values(allocation).reduce((total, value) => total + value, 0);

export const InvestorPersonalityPanel = memo(function InvestorPersonalityPanel({
  personality,
  customAllocation,
  onPersonalityChange,
  onCustomAllocationChange,
  onCustomAllocationBalance,
  onSave,
  dirty,
  saving,
  canSave,
  savedAt,
}: Props) {
  const [customEditing, setCustomEditing] = useState(false);
  const [collapseCustomAfterSave, setCollapseCustomAfterSave] = useState(false);
  const activeAllocation = useMemo(
    () => allocationForPersonality(personality, customAllocation),
    [customAllocation, personality],
  );
  const total = allocationTotal(activeAllocation);
  const customTotal = allocationTotal(customAllocation);
  const customDelta = 100 - customTotal;
  const customIsBalanced = customDelta === 0;
  const customStatusTone = customIsBalanced ? "balanced" : customTotal > 100 ? "over" : "under";
  const customStatusLabel = customIsBalanced
    ? "Balanced at 100%"
    : customDelta > 0
      ? `${customDelta}% left to assign`
      : `${Math.abs(customDelta)}% over target`;
  const customMeterWidth = Math.min(100, customTotal);
  const isCustom = personality === "custom";
  const showCustomEditor = isCustom && (customEditing || !customIsBalanced || dirty);
  const saveDisabled = saving || !dirty || !canSave;
  const saveTitle = !canSave ? "Balance custom allocation to 100% before saving" : "Save investor personality";
  const saveStatus = dirty ? "Unsaved" : savedAt ? "Saved" : "Default";

  useEffect(() => {
    if (!isCustom) {
      setCustomEditing(false);
      setCollapseCustomAfterSave(false);
      return;
    }
    if (!customIsBalanced) {
      setCustomEditing(true);
    }
  }, [customIsBalanced, isCustom]);

  useEffect(() => {
    if (!collapseCustomAfterSave || saving) {
      return;
    }
    if (!dirty && canSave) {
      setCustomEditing(false);
    }
    setCollapseCustomAfterSave(false);
  }, [canSave, collapseCustomAfterSave, dirty, saving]);

  const selectPersonality = (nextPersonality: InvestorPersonalityId) => {
    if (nextPersonality === "custom") {
      setCustomEditing(isCustom ? true : !customIsBalanced);
    } else {
      setCustomEditing(false);
    }
    onPersonalityChange(nextPersonality);
  };

  const savePersonality = () => {
    if (isCustom) {
      setCollapseCustomAfterSave(true);
    }
    onSave();
  };

  return (
    <section className="panel investor-personality-panel">
      <div className="panel-heading">
        <h2>Investor Personality</h2>
        <div className="panel-heading-actions">
          <span className={`personality-save-status ${dirty ? "dirty" : ""}`}>{saveStatus}</span>
          <span
            className={
              isCustom && !customIsBalanced ? "allocation-total-pill needs-balance" : "allocation-total-pill"
            }
          >
            {isCustom ? `${customTotal}%` : `${total}%`}
          </span>
          <button
            type="button"
            className="personality-save-button"
            onClick={savePersonality}
            disabled={saveDisabled}
            title={saveTitle}
          >
            <Save size={15} aria-hidden="true" />
            {saving ? "Saving" : "Save"}
          </button>
        </div>
      </div>

      <div className="personality-card-grid" role="list" aria-label="Investor personality">
        {PERSONALITY_OPTIONS.map((option) => {
          const Icon = option.icon;
          const isSelected = personality === option.id;
          return (
            <button
              type="button"
              className={`personality-card ${isSelected ? "active" : ""}`}
              key={option.id}
              onClick={() => selectPersonality(option.id)}
              aria-pressed={isSelected}
            >
              <Icon size={17} aria-hidden="true" />
              <span>
                <strong>{option.title}</strong>
                <small>{option.caption}</small>
              </span>
            </button>
          );
        })}
      </div>

      {showCustomEditor ? (
        <div className="custom-allocation-grid">
          {ALLOCATION_ROWS.map((row) => (
            <label className="allocation-control" key={row.key}>
              <span>
                <strong>{row.label}</strong>
                <em>{customAllocation[row.key]}%</em>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={customAllocation[row.key]}
                onChange={(event) => onCustomAllocationChange(row.key, Number(event.target.value))}
              />
              <input
                type="number"
                min={0}
                max={100}
                step={1}
                value={customAllocation[row.key]}
                onChange={(event) => onCustomAllocationChange(row.key, Number(event.target.value))}
                aria-label={`${row.label} allocation percent`}
              />
            </label>
          ))}
          <div className={`allocation-validation ${customStatusTone}`} role="status">
            <div className="allocation-total-status">
              <strong>{customStatusLabel}</strong>
              <div
                className={`allocation-total-meter ${customTotal > 100 ? "over" : ""}`}
                aria-hidden="true"
              >
                <i style={{ width: `${customMeterWidth}%` }} />
              </div>
            </div>
            {!customIsBalanced ? (
              <button type="button" onClick={onCustomAllocationBalance}>
                Auto-balance
              </button>
            ) : (
              !dirty && (
                <button type="button" onClick={() => setCustomEditing(false)}>
                  Done
                </button>
              )
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="allocation-plan-grid">
            {ALLOCATION_ROWS.map((row) => {
              const value = activeAllocation[row.key];
              const label = personality === "high_risk" && row.highRiskLabel ? row.highRiskLabel : row.label;
              return (
                <div className="allocation-plan-row" key={row.key}>
                  <span>{label}</span>
                  <div aria-hidden="true">
                    <i style={{ width: `${value}%` }} />
                  </div>
                  <strong>{value}%</strong>
                </div>
              );
            })}
          </div>
          {isCustom && (
            <div className="custom-summary-actions">
              <button type="button" onClick={() => setCustomEditing(true)}>
                <Pencil size={15} aria-hidden="true" />
                Edit allocation
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
});
