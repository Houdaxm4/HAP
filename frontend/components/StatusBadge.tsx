import type { AnalysisStatus } from "@/lib/types";

const statusStyles: Record<AnalysisStatus, string> = {
  Running: "bg-hap-info/15 text-hap-info border-hap-info/30",
  Queued: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  Review: "bg-hap-success/15 text-hap-success border-hap-success/30",
  Complete: "bg-hap-muted/15 text-hap-muted border-hap-muted/30",
  created: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  uploaded: "bg-hap-info/15 text-hap-info border-hap-info/30",
};

function formatStatusLabel(status: AnalysisStatus): string {
  if (status === "created") return "Created";
  if (status === "uploaded") return "Uploaded";
  return status;
}

export default function StatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <span
      className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium capitalize ${statusStyles[status]}`}
    >
      {formatStatusLabel(status)}
    </span>
  );
}
