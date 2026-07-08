export const PIPELINE_STAGES = [
  "upload",
  "parse_workbook",
  "parse_custom_run",
  "fetch_sec_filings",
  "fill_workbook",
  "validate_workbook",
  "complete",
] as const;

export type PipelineStageId = (typeof PIPELINE_STAGES)[number];

export const PIPELINE_STAGE_LABELS: Record<PipelineStageId, string> = {
  upload: "Upload",
  parse_workbook: "Parse Workbook",
  parse_custom_run: "Parse custom_run",
  fetch_sec_filings: "Collect SEC Filings",
  fill_workbook: "Fill Workbook",
  validate_workbook: "Validate Workbook",
  complete: "Complete",
};

export const PIPELINE_STAGE_AGENTS: Record<PipelineStageId, string> = {
  upload: "Document Collection Agent",
  parse_workbook: "Workbook Completion Agent",
  parse_custom_run: "Workbook Completion Agent",
  fetch_sec_filings: "Document Collection Agent",
  fill_workbook: "Workbook Completion Agent",
  validate_workbook: "Workbook Validation Agent",
  complete: "Pipeline Orchestrator",
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "Not started";
  return PIPELINE_STAGE_LABELS[stage as PipelineStageId] ?? stage;
}

export function isProcessingStatus(displayStatus: string): boolean {
  return displayStatus === "Processing" || displayStatus === "Waiting for backend pipeline.";
}
