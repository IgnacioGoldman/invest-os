import {
  ArrowRight,
  Calendar,
  Landmark,
  Lightbulb,
  LineChart as LineIcon,
  LockKeyhole,
  PiggyBank,
  Sparkles,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

const LOGIN_USERNAME = "ignig22";
const LOGIN_PASSWORD = "221722";
const START_YEAR = 2000;
const END_YEAR = 2025;
const MIN_START_YEAR = 2000;
const MAX_END_YEAR = 2025;
const SAVINGS_RATE = 0.03;
const INDEX_RATE = 0.07;
const EUR_INFLATION_RATES = [
  2.3, 2.3, 2.1, 2.1, 2.2, 2.2, 2.1, 3.3, 0.3, 1.6, 2.7, 2.5, 1.4, 0.4, 0.2, 0.2, 1.5, 1.8, 1.2, 0.3,
  2.6, 8.4, 5.4, 2.4, 2,
];

type LandingLoginProps = {
  onLogin: () => void;
};

type GrowthRow = {
  year: number;
  cash: number;
  buyingPower: number;
  savings: number;
  index: number;
};

type GrowthSeriesKey = "cash" | "buyingPower" | "savings" | "index";

const SERIES = [
  { key: "cash", label: "Cash left alone", color: "#a5adbd", strokeWidth: 2.2 },
  { key: "buyingPower", label: "Same buying power", color: "#d7a03a", strokeWidth: 2.4 },
  { key: "savings", label: "Savings account 3%/year", color: "#6d8fff", strokeWidth: 2.8 },
  { key: "index", label: "Global stock index 7%/year", color: "#58d68d", strokeWidth: 3.6 },
] satisfies { key: GrowthSeriesKey; label: string; color: string; strokeWidth: number }[];

const fmt = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const inflationRateForYear = (year: number) => EUR_INFLATION_RATES[year - START_YEAR - 1] ?? 2.2;

function getTicks(start: number, end: number): number[] {
  const ticks: number[] = [];
  const first = Math.ceil(start / 5) * 5;
  for (let year = first; year <= end; year += 5) {
    ticks.push(year);
  }
  if (ticks[0] !== start) {
    ticks.unshift(start);
  }
  if (ticks[ticks.length - 1] !== end) {
    ticks.push(end);
  }
  return [...new Set(ticks)].sort((left, right) => left - right);
}

function buildSeries(amount: number, startYear: number, endYear: number): GrowthRow[] {
  let inflationFactor = 1;
  let savingsFactor = 1;
  let indexFactor = 1;
  const rows: GrowthRow[] = [
    {
      year: startYear,
      cash: amount,
      buyingPower: amount,
      savings: amount,
      index: amount,
    },
  ];

  for (let year = startYear + 1; year <= endYear; year += 1) {
    inflationFactor *= 1 + inflationRateForYear(year) / 100;
    savingsFactor *= 1 + SAVINGS_RATE;
    indexFactor *= 1 + INDEX_RATE;
    rows.push({
      year,
      cash: amount,
      buyingPower: amount / inflationFactor,
      savings: amount * savingsFactor,
      index: amount * indexFactor,
    });
  }

  return rows;
}

function InvestmentGrowthChart({
  data,
  startYear,
  endYear,
  ticks,
}: {
  data: GrowthRow[];
  startYear: number;
  endYear: number;
  ticks: number[];
}) {
  const width = 920;
  const height = 360;
  const padding = { top: 18, right: 22, bottom: 34, left: 64 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(...data.flatMap((row) => SERIES.map((series) => row[series.key])));
  const yMax = Math.max(maxValue * 1.08, 1);
  const xFor = (year: number) => padding.left + ((year - startYear) / Math.max(endYear - startYear, 1)) * plotWidth;
  const yFor = (value: number) => padding.top + plotHeight - (value / yMax) * plotHeight;
  const polylineFor = (key: GrowthSeriesKey) =>
    data.map((row) => `${xFor(row.year).toFixed(2)},${yFor(row[key]).toFixed(2)}`).join(" ");
  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="landing-chart-panel">
      <div className="landing-chart-heading">
        <strong>
          {startYear} → {endYear}
        </strong>
        <span>Every line starts from the same amount in {startYear}.</span>
      </div>
      <div className="landing-chart-scroll">
        <svg
          className="landing-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Growth comparison from ${startYear} to ${endYear}`}
        >
          {gridLines.map((ratio) => {
            const value = yMax * ratio;
            const y = yFor(value);
            return (
              <g key={ratio}>
                <line
                  className={ratio === 0 ? "landing-chart-zero" : "landing-chart-grid"}
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={y}
                  y2={y}
                />
                <text x={padding.left - 10} y={y + 4} textAnchor="end">
                  {ratio === 0 ? "€0" : `€${Math.round(value / 1000)}k`}
                </text>
              </g>
            );
          })}
          {ticks.map((tick) => (
            <text key={tick} className="landing-chart-year" x={xFor(tick)} y={height - 8} textAnchor="middle">
              {tick}
            </text>
          ))}
          {SERIES.map((series) => (
            <polyline
              key={series.key}
              className={`landing-series landing-series-${series.key}`}
              fill="none"
              points={polylineFor(series.key)}
              stroke={series.color}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={series.strokeWidth}
            />
          ))}
        </svg>
      </div>
      <div className="landing-chart-legend" aria-label="Chart legend">
        {SERIES.map((series) => (
          <LegendDot key={series.key} color={series.color} label={series.label} />
        ))}
      </div>
    </div>
  );
}

function ScenarioCard({
  icon: Icon,
  label,
  value,
  sub,
  dotColor,
  tone,
  highlight,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  sub: string;
  dotColor: string;
  tone?: "success" | "warn";
  highlight?: boolean;
}) {
  return (
    <article className={`landing-scenario-card ${tone ?? ""} ${highlight ? "highlight" : ""}`}>
      <div className="landing-scenario-label">
        <span style={{ background: dotColor }} />
        {label}
      </div>
      <strong>{value}</strong>
      <small>
        <Icon size={14} aria-hidden="true" />
        {sub}
      </small>
    </article>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="landing-legend-dot">
      <i style={{ background: color }} />
      {label}
    </span>
  );
}

export function LandingLogin({ onLogin }: LandingLoginProps) {
  const [amount, setAmount] = useState(10000);
  const [startYear, setStartYear] = useState(2000);
  const [endYear, setEndYear] = useState(2025);
  const [username, setUsername] = useState(LOGIN_USERNAME);
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);

  const clampedStart = clamp(startYear, MIN_START_YEAR, MAX_END_YEAR - 1);
  const clampedEnd = clamp(Math.max(endYear, clampedStart + 1), clampedStart + 1, MAX_END_YEAR);
  const duration = clampedEnd - clampedStart;
  const data = useMemo(() => buildSeries(amount || 0, clampedStart, clampedEnd), [amount, clampedEnd, clampedStart]);
  const last = data[data.length - 1];
  const yearTicks = useMemo(() => getTicks(clampedStart, clampedEnd), [clampedEnd, clampedStart]);
  const buyingPowerLost = Math.max(last.cash - last.buyingPower, 0);
  const buyingPowerLostPercent = last.cash > 0 ? Math.round((1 - last.buyingPower / last.cash) * 100) : 0;
  const realValueMultiple = (last.index / Math.max(last.buyingPower, 1)).toFixed(1);

  const submitLogin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (username.trim() === LOGIN_USERNAME && password === LOGIN_PASSWORD) {
      setLoginError(null);
      onLogin();
      return;
    }
    setLoginError("Invalid username or password.");
  };

  const focusLogin = () => {
    document.getElementById("landing-login")?.scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("landing-password")?.focus();
  };

  return (
    <div className="landing-app">
      <main className="landing-shell">
        <div aria-hidden className="landing-glow" />

        <header className="landing-header">
          <span className="landing-pill">
            <Sparkles size={13} aria-hidden="true" />
            Invest OS · The cost of doing nothing
          </span>
        </header>

        <section className="landing-hero">
          <div className="landing-copy">
            <h1>
              If you had <span>{fmt(amount || 0)}</span>
              <br />
              in the year {clampedStart}…
            </h1>
            <p>
              What would it be worth today? See the difference between leaving cash alone, keeping it in a savings
              account, and investing in a global stock index.
            </p>
          </div>

          <form id="landing-login" className="landing-login-card" onSubmit={submitLogin}>
            <div className="landing-login-heading">
              <LockKeyhole size={18} aria-hidden="true" />
              <strong>Login</strong>
            </div>
            <label>
              <span>Username</span>
              <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
            </label>
            <label>
              <span>Password</span>
              <input
                id="landing-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
              />
            </label>
            {loginError && <p>{loginError}</p>}
            <button type="submit">
              Enter app
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </form>
        </section>

        <section className="landing-input-grid" aria-label="Investment comparison inputs">
          <label>
            <span>Your cash back then</span>
            <div className="landing-input-card">
              <div className="landing-big-input">
                <span>€</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  step={500}
                  value={Number.isFinite(amount) ? amount : 0}
                  onChange={(event) => setAmount(Math.max(0, Number(event.target.value)))}
                  placeholder="10000"
                />
              </div>
              <div className="landing-quick-amounts">
                {[1000, 10000, 50000, 100000].map((value) => (
                  <button key={value} type="button" onClick={() => setAmount(value)}>
                    {fmt(value)}
                  </button>
                ))}
              </div>
            </div>
          </label>

          <label>
            <span>Start year</span>
            <div className="landing-input-card">
              <div className="landing-big-input">
                <Calendar size={20} aria-hidden="true" />
                <input
                  type="number"
                  inputMode="numeric"
                  min={MIN_START_YEAR}
                  max={MAX_END_YEAR - 1}
                  value={clampedStart}
                  onChange={(event) => setStartYear(Number(event.target.value))}
                />
              </div>
            </div>
          </label>

          <label>
            <span>End year</span>
            <div className="landing-input-card">
              <div className="landing-big-input">
                <Calendar size={20} aria-hidden="true" />
                <input
                  type="number"
                  inputMode="numeric"
                  min={MIN_START_YEAR + 1}
                  max={MAX_END_YEAR}
                  value={clampedEnd}
                  onChange={(event) => setEndYear(Number(event.target.value))}
                />
              </div>
            </div>
          </label>
        </section>

        <section className="landing-scenario-grid" aria-label="Investment comparison results">
          <ScenarioCard
            icon={Wallet}
            label="Cash left alone"
            value={fmt(last.cash)}
            sub="No growth"
            dotColor="#a5adbd"
          />
          <ScenarioCard
            icon={TrendingUp}
            label="Same buying power"
            value={fmt(last.buyingPower)}
            sub={`${buyingPowerLostPercent}% lost to inflation`}
            dotColor="#d7a03a"
            tone="warn"
          />
          <ScenarioCard
            icon={Landmark}
            label="Savings account"
            value={fmt(last.savings)}
            sub="3% per year"
            dotColor="#6d8fff"
          />
          <ScenarioCard
            icon={LineIcon}
            label="Global stock index"
            value={fmt(last.index)}
            sub="7% per year"
            dotColor="#58d68d"
            tone="success"
            highlight
          />
        </section>

        <InvestmentGrowthChart data={data} startYear={clampedStart} endYear={clampedEnd} ticks={yearTicks} />

        <section className="landing-insight-grid">
          <div className="landing-glass-card">
            <span>The cost of doing nothing</span>
            <p>
              Over <strong>{duration} years</strong>, {fmt(amount || 0)} loses about{" "}
              <strong className="warn">{fmt(buyingPowerLost)}</strong> of buying power sitting still. The global stock
              index example reaches <strong className="success">{fmt(last.index)}</strong>, about{" "}
              <strong>{realValueMultiple}x</strong> the inflation-adjusted value.
            </p>
          </div>
          <div className="landing-cta-card">
            <div>
              <strong>Let Invest OS plan your next {duration} years.</strong>
              <p>Open your dashboard to review your portfolio, notes, recommendations, and risk profile.</p>
            </div>
            <button type="button" onClick={focusLogin}>
              Use login
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </section>

        <section className="landing-fact-grid">
          <div className="landing-glass-card">
            <div className="landing-fact-heading">
              <Lightbulb size={15} aria-hidden="true" />
              Why the chart matters
            </div>
            <p>
              The hard part is not only picking assets. It is keeping cash, savings, and investments aligned with your
              actual plan over many years.
            </p>
          </div>
          <div className="landing-glass-card">
            <div className="landing-fact-heading">
              <PiggyBank size={15} aria-hidden="true" />
              Wealth is managed
            </div>
            <p>
              A portfolio system helps track what you keep, where it sits, and whether your next move matches your risk
              profile.
            </p>
          </div>
        </section>

        <p className="landing-footnote">
          Illustrative. Uses euro inflation data from {clampedStart} to {clampedEnd}, {SAVINGS_RATE * 100}% savings
          growth and {INDEX_RATE * 100}% global index annual growth. Real markets go up and down.
        </p>
      </main>
    </div>
  );
}
