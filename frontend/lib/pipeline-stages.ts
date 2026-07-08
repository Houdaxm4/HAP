import type { AnalysisDetail, AnalysisStatus, PipelineOutputs, PipelineStage } from "./types";

export const PHASE1_STAGES: PipelineStage[] = [
  "filing_collection",
  "workbook_completion",
  "workbook_validation",
];

export const PIPELINE_STAGES: PipelineStage[] = [
  "template_uploaded",
  ...PHASE1_STAGES,
  "fundamental_analysis",
  "market_valuation_analysis",
  "final_recommendation",
];

export const PIPELINE_STAGE_LABELS: Record<PipelineStage, string> = {
  created: "Created",
  template_uploaded: "Template uploaded",
  filing_collection: "Filing collection",
  workbook_completion: "Workbook completion",
  workbook_validation: "Workbook validation",
  fundamental_analysis: "Fundamental analysis",
  market_valuation_analysis: "Market / valuation analysis",
  final_recommendation: "Final recommendation",
  outputs_ready: "Outputs ready",
  failed: "Failed",
};

export const PIPELINE_STAGE_DESCRIPTIONS: Record<PipelineStage, string> = {
  created: "Create the analysis and upload required files.",
  template_uploaded:
    "Prefilled Excel template and custom_run filter are stored for the run.",
  filing_collection:
    "Parse uploads, resolve ticker, and download 10 years of 10-K filings plus the latest 10-Q.",
  workbook_completion:
    "Map SEC facts into the uploaded Excel template without overwriting formulas.",
  workbook_validation:
    "Validate SEC-backed fills across mapped template cells.",
  fundamental_analysis:
    "Run fundamental analysis after Phase 1 workbook completion succeeds.",
  market_valuation_analysis:
    "Run market, competitive, valuation, and value-creation analysis.",
  final_recommendation:
    "Produce investment thesis, risks, recommendation, and final deliverables.",
  outputs_ready:
    "Completed workbook, investment memo, citations, and reports are available.",
  failed: "The pipeline stopped due to an error.",
};

export const PENDING_OUTPUTS: PipelineOutputs = {
  workbook: "pending",
  investment_memo: "pending",
  source_citations: "pending",
  discrepancy_report: "pending",
  verification_report: "pending",
};

export const PIPELINE_PENDING_MESSAGE =
  "Analysis pipeline output pending real backend implementation.";

export function isPhase1Stage(stage: PipelineStage): boolean {
  return PHASE1_STAGES.includes(stage);
}

export function progressForStage(stage: PipelineStage): number {
  if (stage === "outputs_ready") return 100;
  if (stage === "failed") return 0;

  const index = PIPELINE_STAGES.indexOf(stage);
  if (index < 0) {
    return stage === "created" ? 0 : 0;
  }

  return Math.round(((index + 1) / PIPELINE_STAGES.length) * 100);
}

export function statusForStage(
  stage: PipelineStage,
  backendStatus?: string,
): AnalysisStatus {
  if (backendStatus === "processing" || isPhase1Stage(stage)) return "Processing";
  if (stage === "outputs_ready") return "Complete";
  if (stage === "failed") return "Queued";
  if (stage === "created" || stage === "template_uploaded") return "Queued";
  if (stage === "final_recommendation") return "Review";
  return "Running";
}

export function isPipelineComplete(stage: PipelineStage): boolean {
  return stage === "outputs_ready";
}

export function stageIndex(stage: PipelineStage): number {
  if (stage === "created") return -1;
  if (stage === "outputs_ready") return PIPELINE_STAGES.length;
  if (stage === "failed") return -1;
  return PIPELINE_STAGES.indexOf(stage);
}

export function isStageComplete(
  currentStage: PipelineStage,
  stage: PipelineStage,
): boolean {
  return stageIndex(currentStage) > stageIndex(stage);
}

export function isStageCurrent(
  currentStage: PipelineStage,
  stage: PipelineStage,
): boolean {
  return currentStage === stage;
}

export function areOutputsReady(outputs: PipelineOutputs): boolean {
  return Object.values(outputs).every((status) => status === "ready");
}

export const OUTPUT_LABELS: Record<keyof PipelineOutputs, string> = {
  workbook: "Completed Excel workbook",
  investment_memo: "Investment memo",
  source_citations: "Source citations",
  discrepancy_report: "Discrepancy report",
  verification_report: "Confidence / verification report",
};
