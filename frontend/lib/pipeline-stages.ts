export const PIPELINE_STAGES = [
  "workbook_uploaded",
  "workbook_parsed",
  "custom_run_filter_uploaded",
  "custom_run_filter_validated",
  "waiting_for_filing_collection",
  "filings_fetched",
  "provenance_recorded",
  "workbook_validated",
  "validation_report_generated",
  "provenance_report_generated",
  "complete",
] as const;

export type PipelineStageId = (typeof PIPELINE_STAGES)[number];

export const PIPELINE_STAGE_LABELS: Record<PipelineStageId, string> = {
  workbook_uploaded: "Workbook uploaded",
  workbook_parsed: "Workbook parsed",
  custom_run_filter_uploaded: "custom_run_filter uploaded",
  custom_run_filter_validated: "custom_run_filter validated",
  waiting_for_filing_collection: "Waiting for filing collection",
  filings_fetched: "Filings fetched",
  provenance_recorded: "Provenance recorded",
  workbook_validated: "Workbook validated",
  validation_report_generated: "Validation report generated",
  provenance_report_generated: "Provenance report generated",
  complete: "Complete",
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "Not started";
  if (stage === "failed") return "Failed";
  return PIPELINE_STAGE_LABELS[stage as PipelineStageId] ?? stage;
}

export function isActivePipelineStatus(displayStatus: string): boolean {
  return displayStatus === "Processing" || displayStatus === "Uploaded";
}
