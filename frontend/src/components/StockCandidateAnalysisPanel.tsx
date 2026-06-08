import { Brain, Clock3, Sparkles, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { StockCandidate, StockCandidateAnalysis } from "../api";
import { formatDateTime } from "../format";

type Props = {
  analysis: StockCandidateAnalysis | null;
  loading: boolean;
};

function decisionLabel(value: string) {
  return value.replace(/_/g, " ");
}

function CandidateBlock({
  title,
  icon,
  candidate,
}: {
  title: string;
  icon: ReactNode;
  candidate?: StockCandidate | null;
}) {
  if (!candidate) {
    return (
      <article className="stock-candidate-block empty-candidate">
        <div className="stock-candidate-title">
          {icon}
          <h3>{title}</h3>
        </div>
        <p>No clean candidate saved.</p>
      </article>
    );
  }

  return (
    <article className="stock-candidate-block">
      <div className="stock-candidate-title">
        {icon}
        <div>
          <h3>{title}</h3>
          <strong>{candidate.ticker}</strong>
          {candidate.name && <span>{candidate.name}</span>}
        </div>
        <div className="candidate-conviction">
          <strong>{candidate.conviction.toFixed(1)}</strong>
          <span>Conviction</span>
        </div>
      </div>
      <div className="candidate-tags">
        <span>{decisionLabel(candidate.decision)}</span>
        <span>{candidate.entry_quality}</span>
      </div>
      <p className="candidate-thesis">{candidate.thesis}</p>
      <p>
        <strong>Why now:</strong> {candidate.why_now}
      </p>
      {candidate.evidence.length > 0 && (
        <ul>
          {candidate.evidence.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {candidate.main_risks.length > 0 && (
        <div className="candidate-risks">
          {candidate.main_risks.slice(0, 3).map((risk) => (
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
            Analyze Stocks using skills/stock-analysis/stock-entry-analyst.md. Use data/stocks/open_data/*/latest.json and data/stocks/derived_signals/latest.json to find interesting investment candidates. Return evidence-bound JSON and save it to data/stocks/ai_candidate_analysis/latest.json.
          </code>
        </div>
      )}

      {analysis && (
        <>
          <div className="stock-candidate-grid">
            <CandidateBlock
              title="Long-term entry"
              icon={<TrendingUp size={18} aria-hidden="true" />}
              candidate={analysis.best_long_term_candidate}
            />
            <CandidateBlock
              title="Short-term setup"
              icon={<Clock3 size={18} aria-hidden="true" />}
              candidate={analysis.best_short_term_candidate}
            />
          </div>
          {(analysis.runner_ups.length > 0 || analysis.rejected_interesting_names.length > 0) && (
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
          )}
          {analysis.data_quality_notes.length > 0 && (
            <div className="candidate-data-notes">
              {analysis.data_quality_notes.slice(0, 3).map((note) => (
                <span key={note}>{note}</span>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
