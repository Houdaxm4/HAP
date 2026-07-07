import type { AnalysisDetail } from "@/lib/types";
import { isAnalysisComplete } from "@/lib/analysis-completion";
import CompletedAnalysisPanel from "../CompletedAnalysisPanel";

type SummaryTabProps = {
  analysis: AnalysisDetail;
  onViewCompleted: () => void;
};

export default function SummaryTab({ analysis, onViewCompleted }: SummaryTabProps) {
  const isComplete = isAnalysisComplete(analysis);

  return (
    <div className="space-y-6">
      {isComplete && (
        <div id="completed-analysis-summary">
          <CompletedAnalysisPanel
            analysis={analysis}
            onViewCompleted={onViewCompleted}
          />
        </div>
      )}

      <div className="rounded border border-hap-border bg-hap-panel p-6">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          {isComplete ? "Completed Analysis Summary" : "Executive Summary"}
        </h3>
        <p className="mt-4 text-sm leading-relaxed text-foreground/90">
          {analysis.executiveSummary}
        </p>

        {isComplete && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
              <p className="text-xs uppercase tracking-wider text-hap-muted">Rating</p>
              <p className="mt-1 font-medium text-hap-success">{analysis.rating}</p>
            </div>
            <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
              <p className="text-xs uppercase tracking-wider text-hap-muted">Price Target</p>
              <p className="mt-1 font-mono font-medium text-hap-orange">
                {analysis.priceTarget}
              </p>
            </div>
            <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
              <p className="text-xs uppercase tracking-wider text-hap-muted">Workbook Sheets</p>
              <p className="mt-1 font-mono font-medium">{analysis.workbookSheets.length}</p>
            </div>
            <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
              <p className="text-xs uppercase tracking-wider text-hap-muted">Verification Checks</p>
              <p className="mt-1 font-mono font-medium">
                {analysis.verificationChecks.length}
              </p>
            </div>
          </div>
        )}

        {!isComplete && (
          <div className="mt-6 flex gap-3">
            <button
              type="button"
              disabled
              className="rounded border border-hap-border px-4 py-2 text-sm text-hap-muted"
            >
              Export PDF
            </button>
            <button
              type="button"
              disabled
              className="rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange opacity-70"
            >
              Approve &amp; Publish
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
