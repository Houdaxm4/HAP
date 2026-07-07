import { ensureCompletionState, finalizeAnalysis } from "./analysis-completion";
import type { AnalysisDetail, AnalysisStatus } from "./types";

export const QUEUED_MAX_PROGRESS = 20;
export const RUNNING_MAX_PROGRESS = 95;
export const COMPLETE_PROGRESS = 100;

/** Legacy cap left analyses stuck at 94% while Review required >= 95. */
export const STUCK_RUNNING_THRESHOLD = 94;

export const QUEUED_STEP = 2;
export const RUNNING_STEP = 3;
export const REVIEW_STEP = 1;

export const ANALYSIS_STORAGE_KEY = "hap-analysis-state";
export const ANALYSIS_STORAGE_VERSION = 3;

export type PersistedAnalysisState = {
  version: number;
  analyses: AnalysisDetail[];
};

function clampProgress(progress: number): number {
  const value = Number(progress);
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(COMPLETE_PROGRESS, Math.round(value)));
}

export function resolveStatus(progress: number): AnalysisStatus {
  const p = clampProgress(progress);
  if (p >= COMPLETE_PROGRESS) return "Complete";
  if (p >= RUNNING_MAX_PROGRESS) return "Review";
  if (p >= QUEUED_MAX_PROGRESS) return "Running";
  return "Queued";
}

export function advanceProgress(progress: number): number {
  const p = clampProgress(progress);
  if (p >= COMPLETE_PROGRESS) return COMPLETE_PROGRESS;
  if (p >= RUNNING_MAX_PROGRESS) {
    return Math.min(COMPLETE_PROGRESS, p + REVIEW_STEP);
  }
  if (p >= QUEUED_MAX_PROGRESS) {
    return Math.min(RUNNING_MAX_PROGRESS, p + RUNNING_STEP);
  }
  return Math.min(QUEUED_MAX_PROGRESS, p + QUEUED_STEP);
}

/**
 * Repair analyses stuck by the legacy 94% Running cap or status/progress drift.
 */
export function repairAnalysis(analysis: AnalysisDetail): AnalysisDetail {
  const progress = clampProgress(analysis.progress);

  if (analysis.status === "Complete") {
    return ensureCompletionState({
      ...analysis,
      progress: COMPLETE_PROGRESS,
      status: "Complete",
    });
  }

  if (
    analysis.status === "Running" &&
    progress >= STUCK_RUNNING_THRESHOLD &&
    progress < RUNNING_MAX_PROGRESS
  ) {
    return {
      ...analysis,
      progress: RUNNING_MAX_PROGRESS,
      status: "Review",
    };
  }

  const resolvedStatus = resolveStatus(progress);
  if (resolvedStatus !== analysis.status) {
    return { ...analysis, progress, status: resolvedStatus };
  }

  return { ...analysis, progress, status: analysis.status };
}

export function tickAnalysis(analysis: AnalysisDetail): AnalysisDetail {
  const repaired = repairAnalysis(analysis);
  if (repaired.status === "Complete" && repaired.progress >= COMPLETE_PROGRESS) {
    return ensureCompletionState(repaired);
  }

  const nextProgress = advanceProgress(repaired.progress);
  const nextStatus = resolveStatus(nextProgress);

  const nextAnalysis = {
    ...repaired,
    progress: nextProgress,
    status: nextStatus,
  };

  if (nextStatus === "Complete") {
    return finalizeAnalysis(nextAnalysis);
  }

  return nextAnalysis;
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

  const analyses =
    value.analyses.length > 0 ? value.analyses : fallback;

  if (value.version < ANALYSIS_STORAGE_VERSION) {
    return repairAnalyses(analyses);
  }

  return repairAnalyses(analyses);
}

export function readPersistedAnalyses(
  fallback: AnalysisDetail[],
): AnalysisDetail[] {
  if (typeof window === "undefined") return fallback;

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
