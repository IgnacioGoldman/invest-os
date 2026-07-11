import { memo, useMemo } from "react";
import { Flame, Gauge, Leaf, Save, ShieldCheck, SlidersHorizontal } from "lucide-react";

export type InvestorPersonalityId =
  | "capital_preservation"
  | "steady_growth"
  | "balanced_conviction"
  | "aggressive_growth"
  | "high_risk_explorer"
  | "starter"
  | "custom"
  | "low_risk"
  | "high_risk";
export type InvestorAllocationKey = "vwce" | "cashBonds" | "individualStocks" | "crypto";
export type InvestorAllocation = Record<InvestorAllocationKey, number>;

type PersonaId = Exclude<InvestorPersonalityId, "custom" | "low_risk" | "high_risk">;

type Persona = {
  id: PersonaId;
  name: string;
  tag: string;
  icon: typeof ShieldCheck;
  allocation: InvestorAllocation;
  vibe: string;
  goodFor: string[];
  tradeoffs: string[];
  example: string;
};

type Bucket = {
  key: InvestorAllocationKey;
  miniLabel: string;
  label: string;
  short: string;
  tone: "primary" | "success" | "accent" | "warning";
  plain: string;
};

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

export const CAPITAL_PRESERVATION_ALLOCATION: InvestorAllocation = {
  vwce: 40,
  cashBonds: 55,
  individualStocks: 5,
  crypto: 0,
};

export const STEADY_GROWTH_ALLOCATION: InvestorAllocation = {
  vwce: 70,
  cashBonds: 20,
  individualStocks: 10,
  crypto: 0,
};

export const BALANCED_CONVICTION_ALLOCATION: InvestorAllocation = {
  vwce: 55,
  cashBonds: 15,
  individualStocks: 25,
  crypto: 5,
};

export const AGGRESSIVE_GROWTH_ALLOCATION: InvestorAllocation = {
  vwce: 45,
  cashBonds: 5,
  individualStocks: 35,
  crypto: 15,
};

export const LOW_RISK_ALLOCATION = STEADY_GROWTH_ALLOCATION;
export const HIGH_RISK_ALLOCATION = AGGRESSIVE_GROWTH_ALLOCATION;
export const DEFAULT_CUSTOM_ALLOCATION = BALANCED_CONVICTION_ALLOCATION;
export const DEFAULT_INVESTOR_PERSONALITY: InvestorPersonalityId = "steady_growth";

export const normalizeInvestorPersonalityId = (personality: InvestorPersonalityId): InvestorPersonalityId => {
  if (personality === "low_risk") return "steady_growth";
  if (personality === "high_risk") return "aggressive_growth";
  if (personality === "high_risk_explorer") return "aggressive_growth";
  if (personality === "starter") return "steady_growth";
  return personality;
};

const PERSONAS: Persona[] = [
  {
    id: "capital_preservation",
    name: "Capital Preservation",
    tag: "Sleep-well portfolio",
    icon: ShieldCheck,
    allocation: CAPITAL_PRESERVATION_ALLOCATION,
    vibe: "You care more about not losing money than about hitting home runs. Slow, steady, boring in the best way.",
    goodFor: ["Nearing a big purchase", "You panic when markets drop 10%", "Money you cannot afford to lose"],
    tradeoffs: ["Growth will feel slow in bull markets", "Inflation is your main enemy, not crashes"],
    example: "Think of a retired teacher who wants their savings to last 25 years, not double in 5.",
  },
  {
    id: "steady_growth",
    name: "Steady Growth",
    tag: "Bigger core, calmer ride",
    icon: Leaf,
    allocation: STEADY_GROWTH_ALLOCATION,
    vibe: "You want the market's long-term growth without the drama. Most of your money quietly compounds in global index funds.",
    goodFor: ["10+ year horizon", "You check your portfolio monthly, not daily", "Building wealth alongside a career"],
    tradeoffs: ["You will not beat the market, but you probably will not lose to it either", "Occasional 20% drawdowns are the price of admission"],
    example: "Think of a 35-year-old software engineer buying VWCE every month and ignoring the news.",
  },
  {
    id: "balanced_conviction",
    name: "Balanced Conviction",
    tag: "Core + a few strong bets",
    icon: Gauge,
    allocation: BALANCED_CONVICTION_ALLOCATION,
    vibe: "The core is on autopilot, but you also back a handful of companies or themes you genuinely believe in.",
    goodFor: ["You enjoy researching stocks", "You have opinions on specific companies", "You can stomach single-stock volatility"],
    tradeoffs: ["Your bets might underperform the index", "Requires ongoing attention and honest self-review"],
    example: "Think of someone who owns a global index, plus meaningful positions in Nvidia and ASML because they work in tech.",
  },
  {
    id: "aggressive_growth",
    name: "Aggressive Growth",
    tag: "More conviction and crypto",
    icon: Flame,
    allocation: AGGRESSIVE_GROWTH_ALLOCATION,
    vibe: "You are playing offense. Long horizon, high tolerance for pain, chasing serious upside.",
    goodFor: ["20+ year horizon", "Stable income you do not need to touch", "You have lived through a 50% drawdown and stayed invested"],
    tradeoffs: ["Expect brutal years, including 30% drawdowns or worse", "Concentration risk is real"],
    example: "Think of a 28-year-old with no dependents who kept buying through the 2022 crypto crash.",
  },
];

const BUCKETS: Bucket[] = [
  {
    key: "vwce",
    miniLabel: "Core",
    label: "Core global equities",
    short: "Your growth engine",
    tone: "primary",
    plain: "Broad, boring index funds like a global stock ETF that quietly compound over decades.",
  },
  {
    key: "cashBonds",
    miniLabel: "Def.",
    label: "Defensive assets",
    short: "Your shock absorbers",
    tone: "success",
    plain: "Cash, bonds, gold, or similar diversifiers that help you avoid selling stocks at a bad time.",
  },
  {
    key: "individualStocks",
    miniLabel: "Active",
    label: "Active equities",
    short: "Your conviction bets",
    tone: "accent",
    plain: "Individual stocks or focused funds you believe in. Higher effort, higher variance.",
  },
  {
    key: "crypto",
    miniLabel: "Crypto",
    label: "Crypto / speculative",
    short: "High-volatility sleeve",
    tone: "warning",
    plain: "Bitcoin, ETH, and other high-volatility bets. Small slice, huge swings.",
  },
];

const PERSONA_BY_ID = new Map(PERSONAS.map((persona) => [persona.id, persona]));

export function allocationForPersonality(
  personality: InvestorPersonalityId,
  customAllocation: InvestorAllocation,
): InvestorAllocation {
  const normalized = normalizeInvestorPersonalityId(personality);
  if (normalized === "custom") return customAllocation;
  return PERSONA_BY_ID.get(normalized as PersonaId)?.allocation ?? STEADY_GROWTH_ALLOCATION;
}

const allocationTotal = (allocation: InvestorAllocation) =>
  Object.values(allocation).reduce((total, value) => total + value, 0);

const describeCustom = (allocation: InvestorAllocation) => {
  const parts: string[] = [];
  if (allocation.vwce >= 60) parts.push("mostly riding the global market");
  else if (allocation.vwce >= 40) parts.push("using indexes as a solid base");
  else parts.push("light on passive exposure");
  if (allocation.cashBonds >= 30) parts.push("with strong shock absorbers");
  else if (allocation.cashBonds >= 10) parts.push("keeping some defensive ballast");
  if (allocation.individualStocks >= 25) parts.push("plus real conviction bets");
  if (allocation.crypto >= 20) parts.push("and a heavy crypto sleeve");
  else if (allocation.crypto >= 5) parts.push("and a small speculative sleeve");
  return `You are ${parts.join(", ")}. Expect the ride to match: bigger crypto and active weights mean bigger swings.`;
};

function MiniBar({ label, pct, tone }: { label: string; pct: number; tone: Bucket["tone"] }) {
  return (
    <div className="personality-mini-bar">
      <div className="personality-mini-track" aria-hidden="true">
        <i className={`tone-${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <div>
        <span>{label}</span>
        <strong>{pct}%</strong>
      </div>
    </div>
  );
}

function InfoBlock({ title, items, tone }: { title: string; items: string[]; tone: "success" | "warning" }) {
  return (
    <div className="personality-info-block">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>
            <i className={`tone-${tone}`} aria-hidden="true" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

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
  const normalizedPersonality = normalizeInvestorPersonalityId(personality);
  const activeAllocation = useMemo(
    () => allocationForPersonality(personality, customAllocation),
    [customAllocation, personality],
  );
  const selectedPersona = normalizedPersonality === "custom"
    ? null
    : PERSONA_BY_ID.get(normalizedPersonality as PersonaId) ?? PERSONAS[1];
  const total = allocationTotal(activeAllocation);
  const customTotal = allocationTotal(customAllocation);
  const isCustom = normalizedPersonality === "custom";
  const saveDisabled = saving || !dirty || !canSave;
  const saveTitle = !canSave ? "Balance custom allocation to 100% before saving" : "Save investor personality";
  const saveStatus = dirty ? "Unsaved" : savedAt ? "Saved" : "Default";

  return (
    <div className="personality-shell">
      <header className="personality-hero">
        <div>
          <h2>Investor Personality</h2>
          <p>Pick the style that fits you. Everything else in Invest OS adapts to it.</p>
        </div>
        <div className="personality-status-card">
          <div className="personality-status-pills">
            <span className={`personality-save-status ${dirty ? "dirty" : ""}`}>{saveStatus}</span>
            <span className={isCustom && customTotal !== 100 ? "allocation-total-pill needs-balance" : "allocation-total-pill"}>
              {isCustom ? `${customTotal}%` : `${total}%`}
            </span>
          </div>
          <button
            type="button"
            className="personality-save-button"
            onClick={onSave}
            disabled={saveDisabled}
            title={saveTitle}
          >
            <Save size={15} aria-hidden="true" />
            {saving ? "Saving" : "Save"}
          </button>
        </div>
      </header>

      <div className="personality-card-grid" role="list" aria-label="Investor personality">
        {PERSONAS.map((persona) => {
          const Icon = persona.icon;
          const isSelected = normalizedPersonality === persona.id;
          return (
            <button
              type="button"
              className={`personality-card ${isSelected ? "active" : ""}`}
              key={persona.id}
              onClick={() => onPersonalityChange(persona.id)}
              aria-pressed={isSelected}
            >
              <div className="personality-card-header">
                <span className="personality-card-icon">
                  <Icon size={18} aria-hidden="true" />
                </span>
                <span>
                  <strong>{persona.name}</strong>
                  <small>{persona.tag}</small>
                </span>
              </div>
              <div className="personality-mini-grid">
                {BUCKETS.map((bucket) => (
                  <MiniBar
                    key={bucket.key}
                    label={bucket.miniLabel}
                    pct={persona.allocation[bucket.key]}
                    tone={bucket.tone}
                  />
                ))}
              </div>
            </button>
          );
        })}

        <button
          type="button"
          className={`personality-card personality-custom-card ${isCustom ? "active" : ""}`}
          onClick={() => onPersonalityChange("custom")}
          aria-pressed={isCustom}
        >
          <div className="personality-card-header">
            <span className="personality-card-icon">
              <SlidersHorizontal size={18} aria-hidden="true" />
            </span>
            <span>
              <strong>Custom</strong>
              <small>Set your own targets below</small>
            </span>
          </div>
          <div className="personality-mini-grid">
            {BUCKETS.map((bucket) => (
              <MiniBar
                key={bucket.key}
                label={bucket.miniLabel}
                pct={customAllocation[bucket.key]}
                tone={bucket.tone}
              />
            ))}
          </div>
        </button>
      </div>

      {isCustom && (
        <div className="personality-target-panel">
          <div className="personality-section-heading">
            <div>
              <small>Your target mix</small>
              <strong>Custom</strong>
            </div>
            <span>Must add up to 100%</span>
          </div>
          <div className="custom-allocation-grid">
            {BUCKETS.map((bucket) => (
              <label className={`allocation-control tone-${bucket.tone}`} key={bucket.key}>
                <span>
                  <strong>{bucket.label}</strong>
                  <em>{activeAllocation[bucket.key]}%</em>
                </span>
                <small>{bucket.short}</small>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={activeAllocation[bucket.key]}
                  onChange={(event) => onCustomAllocationChange(bucket.key, Number(event.target.value))}
                />
                <p>{bucket.plain}</p>
              </label>
            ))}
            {customTotal !== 100 && (
              <div className={`allocation-validation ${customTotal > 100 ? "over" : "under"}`} role="status">
                <div className="allocation-total-status">
                  <strong>{customTotal > 100 ? `${customTotal - 100}% over target` : `${100 - customTotal}% left to assign`}</strong>
                  <div className={`allocation-total-meter ${customTotal > 100 ? "over" : ""}`} aria-hidden="true">
                    <i style={{ width: `${Math.min(100, customTotal)}%` }} />
                  </div>
                </div>
                <button type="button" onClick={onCustomAllocationBalance}>
                  Auto-balance
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="personality-explanation-panel">
        <div className="personality-section-heading">
          <div>
            <small>Your profile, in plain words</small>
            <strong>{isCustom ? "Your custom mix" : selectedPersona?.name ?? "Steady Growth"}</strong>
          </div>
        </div>
        <p>{isCustom ? describeCustom(activeAllocation) : selectedPersona?.vibe}</p>

        {!isCustom && selectedPersona && (
          <div className="personality-info-grid">
            <InfoBlock title="This fits you if..." items={selectedPersona.goodFor} tone="success" />
            <InfoBlock title="What you are accepting" items={selectedPersona.tradeoffs} tone="warning" />
          </div>
        )}

        <div className="personality-example-box">
          <small>Real-life example</small>
          <p>
            {isCustom
              ? "Adjust the sliders to match a persona above and the app will use your custom target mix."
              : selectedPersona?.example}
          </p>
        </div>
        <footer>Not financial advice. Personalities are frameworks; your real plan depends on goals, income, and time horizon.</footer>
      </div>
    </div>
  );
});
