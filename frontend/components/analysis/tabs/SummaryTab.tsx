import type { AnalysisRecord } from "@/lib/types";

export default function SummaryTab({ analysis }: { analysis: AnalysisRecord }) {
  const isComplete = analysis.displayStatus === "Complete";

  return (
    <div className="rounded border border-hap-border bg-hap-panel p-6">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
        Investment Memo
      </h3>
      {isComplete ? (
        <p className="mt-4 text-sm leading-relaxed text-foreground/90">
          Workbook milestone 1 is complete. Fundamental analysis and the investment memo
          will be generated in a later pipeline stage.
        </p>
      ) : (
        <p className="mt-4 text-sm leading-relaxed text-hap-muted">
          The investment memo is not available yet. HAP will only produce it after the
          workbook pipeline completes and fundamental analysis begins.
        </p>
      )}
    </div>
  );
}
