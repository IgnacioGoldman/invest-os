import { Check, Copy, ExternalLink, Sparkles, X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { StockAnalysisBrief } from "../aiAnalysis";
import "../aiAnalysis.css";

export type AnalysisCopyStatus = "copying" | "copied" | "error";

export function StockAnalysisDialog({ brief, copyStatus, onCopy, onClose }: {
  brief: StockAnalysisBrief;
  copyStatus: AnalysisCopyStatus;
  onCopy: () => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    dialog?.showModal();
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus({ preventScroll: true });
    };
  }, []);
  const count = brief.tickers.length;
  return (
    <dialog ref={dialogRef} className="stock-analysis-dialog" aria-labelledby="stock-analysis-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="stock-analysis-content">
        <header>
          <Sparkles size={25} aria-hidden="true" />
          <h2 id="stock-analysis-title">Your analysis prompt is ready</h2>
          <button type="button" className="stock-analysis-close" aria-label="Close analysis prompt" onClick={onClose}><X size={21} /></button>
        </header>
        <p>We've prepared a detailed prompt for your {count} selected stock{count === 1 ? "" : "s"}.</p>
        <div className="stock-analysis-tickers" aria-label="Selected stocks">{brief.tickers.map((ticker) => <span key={ticker}>{ticker}</span>)}</div>
        <div className="stock-analysis-buttons">
          <button type="button" className="stock-analysis-copy" onClick={onCopy} disabled={copyStatus === "copying"}>
            {copyStatus === "copied" ? <Check size={20} /> : <Copy size={20} />}
            {copyStatus === "copying" ? "Copying prompt…" : copyStatus === "copied" ? "Copied · Copy again" : "Copy analysis prompt"}
          </button>
          <a href="https://chatgpt.com/" target="_blank" rel="noreferrer" className="stock-analysis-open">Open ChatGPT<ExternalLink size={18} /></a>
        </div>
        {copyStatus === "error" ? (
          <p className="stock-analysis-copy-error" role="alert">Automatic copy didn't work. Try Copy analysis prompt, or select the full prompt below to copy it.</p>
        ) : <p className="stock-analysis-instruction" role="status">{copyStatus === "copied" ? "Prompt copied. Paste it into ChatGPT or your preferred AI to start your analysis." : "Copying your prompt…"}</p>}
        <section className="stock-analysis-preview" aria-label="AI brief preview"><h3>AI brief preview</h3><p>{brief.preview}</p></section>
        <details className="stock-analysis-full" open={copyStatus === "error" ? true : undefined}>
          <summary>View full prompt</summary>
          <textarea ref={promptRef} readOnly rows={8} value={brief.prompt} aria-label="Full analysis prompt" spellCheck={false} />
          <button type="button" onClick={() => { promptRef.current?.focus(); promptRef.current?.select(); }}>Select prompt to copy manually</button>
        </details>
      </div>
    </dialog>
  );
}
