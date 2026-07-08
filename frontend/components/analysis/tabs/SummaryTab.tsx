import type { AnalysisDetail } from "@/lib/types";
import { isAnalysisComplete } from "@/lib/analysis-pipeline";
import { PIPELINE_PENDING_MESSAGE } from "@/lib/pipeline-stages";
import PipelineOutputsPanel from "../PipelineOutputsPanel";

type SummaryTabProps = {
  analysis: AnalysisDetail;
  onViewSummary: () => void;
};

export default function SummaryTab({ analysis, onViewSummary }: SummaryTabProps) {
  const isComplete = isAnalysisComplete(analysis);

  return (
    <div id="analysis-summary" className="space-y-6">
      <PipelineOutputsPanel analysis={analysis} onViewSummary={onViewSummary} />

      <div className="rounded border border-hap-border bg-hap-panel p-6">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          {isComplete ? "Completed analysis summary" : "Pipeline status"}
        </h3>
        <p className="mt-4 text-sm leading-relaxed text-foreground/90">
          {isComplete
            ? analysis.executiveSummary
            : analysis.executiveSummary || PIPELINE_PENDING_MESSAGE}
        </p>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
            <p className="text-xs uppercase tracking-wider text-hap-muted">Current stage</p>
            <p className="mt-1 font-medium">{analysis.pipelineStage.replaceAll("_", " ")}</p>
          </div>
          <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
            <p className="text-xs uppercase tracking-wider text-hap-muted">Backend</p>
            <p className="mt-1 font-medium">
              {analysis.backendConnected ? "Connected" : "Offline / local only"}
            </p>
          </div>
          <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
            <p className="text-xs uppercase tracking-wider text-hap-muted">Prefilled template</p>
            <p className="mt-1 text-sm">{analysis.uploadedFiles.prefilledWorkbook ?? "—"}</p>
          </div>
          <div className="rounded border border-hap-border bg-hap-panel-elevated p-4">
            <p className="text-xs uppercase tracking-wider text-hap-muted">custom_run filter</p>
            <p className="mt-1 text-sm">{analysis.uploadedFiles.customRunFilter ?? "—"}</p>
          </div>
        </div>

        {analysis.isDemo && (
          <p className="mt-4 rounded border border-hap-warning/30 bg-hap-warning/10 px-3 py-2 text-xs text-hap-warning">
            Demo fixture only. Create a new analysis with uploads to exercise the real workflow.
          </p>
        )}
      </div>
    </div>
  );
}
