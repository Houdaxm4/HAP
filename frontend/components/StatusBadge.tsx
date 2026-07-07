import type { AnalysisStatus } from "@/lib/types";

const statusStyles: Record<AnalysisStatus, string> = {
  Running: "bg-hap-info/15 text-hap-info border-hap-info/30",
  Queued: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  Review: "bg-hap-success/15 text-hap-success border-hap-success/30",
  Complete: "bg-hap-muted/15 text-hap-muted border-hap-muted/30",
};

export default function StatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <span
      className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${statusStyles[status]}`}
    >
      {status}
    </span>
  );
}
