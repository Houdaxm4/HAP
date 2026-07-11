import type { DisplayStatus } from "@/lib/types";

const statusStyles: Record<DisplayStatus, string> = {
  Created: "bg-hap-muted/15 text-hap-muted border-hap-muted/30",
  Uploaded: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  Processing: "bg-hap-info/15 text-hap-info border-hap-info/30",
  "Waiting for filing collection": "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  "Filings collected": "bg-hap-success/15 text-hap-success border-hap-success/30",
  "Statements extracted": "bg-hap-success/15 text-hap-success border-hap-success/30",
  Complete: "bg-hap-success/15 text-hap-success border-hap-success/30",
  Failed: "bg-red-500/15 text-red-400 border-red-500/30",
};

export default function StatusBadge({ status }: { status: DisplayStatus | string }) {
  const style =
    status in statusStyles
      ? statusStyles[status as DisplayStatus]
      : "bg-hap-muted/15 text-hap-muted border-hap-muted/30";

  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
