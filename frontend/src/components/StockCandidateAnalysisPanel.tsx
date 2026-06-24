import { Brain, Clock3, Info, Sparkles, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { StockCandidate, StockCandidateAnalysis } from "../api";
import { formatDateTime } from "../format";

type Props = {
  analysis: StockCandidateAnalysis | null;
  loading: boolean;
};

type Tone = "good" | "watch" | "bad";

const CANDIDATE_DESCRIPTIONS = {
  longTerm:
    "Optimized for durable ownership. Strong business, reasonable valuation, good derived signals, and price not terrible. Support zone helps, but it should not dominate.",
  tactical:
    "Optimized for timing. Price action, support zone, pullback, near-term risk/reward, momentum stabilization. Business still cannot be awful, but this can be more about where would I enter now.",
};

function decisionLabel(value: string) {
  return value.replace(/_/g, " ");
}

function convictionTone(value: number): Tone {
  if (value < 4) return "bad";
  if (value < 8) return "watch";
  return "good";
}

function CandidateBlock({
  title,
  description,
  icon,
  candidate,
}: {
  title: string;
  description: string;
  icon: ReactNode;
  candidate?: StockCandidate | null;
}) {
  const evidenceOptions: Array<[string, string[]]> = candidate
    ? [
        ["Business", candidate.business_evidence ?? []],
        ["Valuation", candidate.valuation_evidence ?? []],
        ["Price", candidate.price_evidence ?? []],
        ["Support 1D", candidate.support_1d_evidence ?? []],
        ["Derived", candidate.derived_signal_evidence ?? []],
        ["Evidence", candidate.evidence ?? []],
      ]
    : [];
  const evidenceSections = evidenceOptions.filter(([, items]) => items.length > 0);
  const risks = candidate ? (candidate.key_risks?.length ? candidate.key_risks : candidate.main_risks) : [];

  if (!candidate) {
    return (
      <article className="stock-candidate-block empty-candidate">
        <div className="stock-candidate-title">
          {icon}
          <div className="candidate-heading-line">
            <h3>{title}</h3>
            <button className="candidate-info-button" type="button" aria-label={`${title} definition`} title={description}>
              <Info size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
        <p>{title} not found.</p>
      </article>
    );
  }

  return (
    <article className="stock-candidate-block">
      <div className="stock-candidate-title">
        {icon}
        <div>
          <div className="candidate-heading-line">
            <h3>{title}</h3>
            <button className="candidate-info-button" type="button" aria-label={`${title} definition`} title={description}>
              <Info size={14} aria-hidden="true" />
            </button>
          </div>
          <strong>{candidate.ticker}</strong>
          {candidate.name && <span>{candidate.name}</span>}
        </div>
        <div className={`candidate-conviction ${convictionTone(candidate.conviction)}`}>
          <strong>{candidate.conviction.toFixed(1)}</strong>
          <span>Conviction</span>
        </div>
      </div>
      <div className="candidate-tags">
        <span>{decisionLabel(candidate.decision)}</span>
        <span>{candidate.entry_quality}</span>
      </div>
      <p className="candidate-thesis">{candidate.thesis}</p>
      {evidenceSections.length > 0 && (
        <div className="candidate-evidence-groups">
          {evidenceSections.slice(0, 5).map(([label, items]) => (
            <div className="candidate-evidence-group" key={label}>
              <span>{label}</span>
              <ul>
                {items.slice(0, 2).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {risks.length > 0 && (
        <div className="candidate-risks">
          {risks.slice(0, 3).map((risk) => (
            <p key={risk}>{risk}</p>
          ))}
        </div>
      )}
    </article>
  );
}

export function StockCandidateAnalysisPanel({ analysis, loading }: Props) {
  return (
    <section className="panel stock-candidate-panel">
      <div className="panel-heading">
        <div className="panel-title-with-info">
          <h2>AI Entry Candidates</h2>
          <span className="candidate-source">
            <Brain size={15} aria-hidden="true" />
            {analysis ? `As of ${analysis.as_of}` : "No saved run"}
          </span>
        </div>
        {analysis && (
          <div className="panel-heading-actions">
            <span>{analysis.live_context_used ? "Live context used" : "Local facts only"}</span>
            <span>{formatDateTime(analysis.generated_at)}</span>
          </div>
        )}
      </div>

      {loading && <p className="loading inline">Loading AI candidate analysis...</p>}

      {!loading && !analysis && (
        <div className="stock-candidate-empty">
          <Sparkles size={18} aria-hidden="true" />
          <p>No saved candidate analysis yet.</p>
          <code>
            Analyze stocks using skills/stock-analysis/stock-entry-analyst.md. Use data/stocks/open_data/*/latest.json and data/stocks/derived_signals/latest.json. Find one long-term accumulation candidate and one tactical entry setup candidate. Ask for missing data only if it blocks the decision. Save the result to data/stocks/ai_candidate_analysis/latest.json.
          </code>
        </div>
      )}

      {analysis && (
        <>
          <div className="stock-candidate-grid">
            <CandidateBlock
              title="Long-term accumulation candidate"
              description={CANDIDATE_DESCRIPTIONS.longTerm}
              icon={<TrendingUp size={18} aria-hidden="true" />}
              candidate={analysis.best_long_term_candidate}
            />
            <CandidateBlock
              title="Tactical entry setup"
              description={CANDIDATE_DESCRIPTIONS.tactical}
              icon={<Clock3 size={18} aria-hidden="true" />}
              candidate={analysis.best_short_term_candidate}
            />
          </div>
          {(analysis.runner_ups.length > 0 || analysis.rejected_interesting_names.length > 0) && (
            <details className="candidate-disclosure">
              <summary>
                <span>Runner-ups and rejected</span>
                <small>
                  {analysis.runner_ups.length + analysis.rejected_interesting_names.length} names
                </small>
              </summary>
              <div className="candidate-secondary-grid">
                {analysis.runner_ups.length > 0 && (
                  <div>
                    <h3>Runner-ups</h3>
                    {analysis.runner_ups.slice(0, 4).map((item) => (
                      <p key={`${item.ticker}-${item.horizon}`}>
                        <strong>{item.ticker}</strong> {item.reason}
                      </p>
                    ))}
                  </div>
                )}
                {analysis.rejected_interesting_names.length > 0 && (
                  <div>
                    <h3>Rejected</h3>
                    {analysis.rejected_interesting_names.slice(0, 4).map((item) => (
                      <p key={item.ticker}>
                        <strong>{item.ticker}</strong> {item.reason}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </details>
          )}
          {analysis.data_quality_notes.length > 0 && (
            <details className="candidate-disclosure candidate-notes-disclosure">
              <summary>
                <span>Analysis notes</span>
                <small>{analysis.data_quality_notes.length} notes</small>
              </summary>
              <div className="candidate-data-notes">
                {analysis.data_quality_notes.slice(0, 3).map((note) => (
                  <span key={note}>{note}</span>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
