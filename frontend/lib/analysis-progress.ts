import type { AnalysisDetail, PipelineStage } from "./types";
import {
  PENDING_OUTPUTS,
  PIPELINE_PENDING_MESSAGE,
  progressForStage,
  statusForStage,
} from "./pipeline-stages";

export const ANALYSIS_STORAGE_KEY = "hap-analysis-state";
export const ANALYSIS_STORAGE_VERSION = 4;

export type PersistedAnalysisState = {
  version: number;
  analyses: AnalysisDetail[];
};

const LEGACY_COMPLETE_STAGES = new Set(["Complete"]);

function normalizePipelineStage(value: unknown): PipelineStage {
  if (typeof value !== "string") return "created";

  const stage = value as PipelineStage;
  const valid: PipelineStage[] = [
    "created",
    "template_uploaded",
    "filing_collection",
    "workbook_completion",
    "workbook_validation",
    "fundamental_analysis",
    "market_valuation_analysis",
    "final_recommendation",
    "outputs_ready",
    "failed",
  ];

  if (valid.includes(stage)) return stage;
  return "created";
}

export function repairAnalysis(analysis: AnalysisDetail): AnalysisDetail {
  const pipelineStage = normalizePipelineStage(analysis.pipelineStage);
  const migratedStage =
    LEGACY_COMPLETE_STAGES.has(String(analysis.status)) ||
    (analysis.progress >= 100 && pipelineStage !== "outputs_ready")
      ? "template_uploaded"
      : pipelineStage;

  return {
    ...analysis,
    backendAnalysisId: analysis.backendAnalysisId ?? null,
    backendConnected: Boolean(analysis.backendConnected),
    isDemo: Boolean(analysis.isDemo),
    pipelineStage: migratedStage,
    pipelineMessage:
      analysis.pipelineMessage ||
      (migratedStage === "outputs_ready"
        ? "Pipeline outputs are ready for review."
        : PIPELINE_PENDING_MESSAGE),
    pipelineOutputs: analysis.pipelineOutputs ?? { ...PENDING_OUTPUTS },
    progress: progressForStage(migratedStage),
    status: statusForStage(migratedStage),
    executiveSummary:
      migratedStage === "outputs_ready"
        ? analysis.executiveSummary
        : analysis.executiveSummary?.includes("has finished")
          ? PIPELINE_PENDING_MESSAGE
          : analysis.executiveSummary || PIPELINE_PENDING_MESSAGE,
    uploadedFiles: analysis.uploadedFiles ?? {
      prefilledWorkbook: null,
      previousWorkbook: null,
      customRunFilter: null,
    },
  };
}

export function repairAnalyses(analyses: AnalysisDetail[]): AnalysisDetail[] {
  return analyses.map(repairAnalysis);
}

export function isPersistedAnalysisState(
  value: unknown,
): value is PersistedAnalysisState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as PersistedAnalysisState;
  return (
    typeof candidate.version === "number" &&
    Array.isArray(candidate.analyses)
  );
}

export function migratePersistedState(
  value: unknown,
  fallback: AnalysisDetail[],
): AnalysisDetail[] {
  if (!isPersistedAnalysisState(value)) {
    return repairAnalyses(fallback);
  }

  const analyses = value.analyses.length > 0 ? value.analyses : fallback;
  return repairAnalyses(analyses);
}

export function readPersistedAnalyses(
  fallback: AnalysisDetail[],
): AnalysisDetail[] {
  if (typeof window === "undefined") return repairAnalyses(fallback);

  try {
    const raw = window.localStorage.getItem(ANALYSIS_STORAGE_KEY);
    if (!raw) return repairAnalyses(fallback);

    return migratePersistedState(JSON.parse(raw), fallback);
  } catch {
    return repairAnalyses(fallback);
  }
}

export function writePersistedAnalyses(analyses: AnalysisDetail[]): void {
  if (typeof window === "undefined") return;

  const payload: PersistedAnalysisState = {
    version: ANALYSIS_STORAGE_VERSION,
    analyses: repairAnalyses(analyses),
  };

  window.localStorage.setItem(ANALYSIS_STORAGE_KEY, JSON.stringify(payload));
}
