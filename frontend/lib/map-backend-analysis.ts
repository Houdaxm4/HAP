import type {
  AnalysisDetail,
  AnalysisDetailDto,
  AnalysisStatus,
  AnalysisSummary,
} from "./types";

const TYPE_LABELS: Record<string, string> = {
  new_company: "New Company Initiation",
  annual_update: "Annual Update",
  quarterly_update: "Quarterly Update",
};

export function mapPipelineToStatus(
  pipelineState: string,
  isComplete: boolean,
  status: string,
): AnalysisStatus {
  if (isComplete || pipelineState === "complete") {
    return "Complete";
  }
  if (pipelineState === "failed" || status === "failed") {
    return "Failed";
  }
  if (pipelineState === "idle" && status === "uploaded") {
    return "Queued";
  }
  if (pipelineState === "processing") {
    return "Running";
  }
  return "Queued";
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function mapSummaryToAnalysisDetail(summary: AnalysisSummary): AnalysisDetail {
  return {
    id: summary.analysis_id,
    company: summary.company,
    ticker: summary.ticker,
    type: TYPE_LABELS[summary.analysis_type] ?? summary.analysis_type,
    status: mapPipelineToStatus(
      summary.pipeline_state,
      summary.is_complete,
      summary.status,
    ),
    progress: summary.progress_pct,
    startedAt: summary.created_at,
    updatedAt: summary.updated_at,
    isComplete: summary.is_complete,
    recommendation: summary.recommendation,
    recommendationLabel: summary.recommendation_label,
    businessQualityScore: summary.business_quality_score,
    investmentAttractivenessScore: summary.investment_attractiveness_score,
    decisionLog: [],
    hasEngineResult: false,
    hasValidationReport: false,
    engineResult: null,
    validationReport: null,
  };
}

export function mapDetailDtoToAnalysisDetail(
  detail: AnalysisDetailDto,
  previous?: AnalysisDetail,
): AnalysisDetail {
  return {
    ...mapSummaryToAnalysisDetail(detail),
    decisionLog: (detail.decision_log ?? []).map((entry, index) => ({
      id: `d-${detail.analysis_id}-${index}`,
      timestamp: formatTimestamp(entry.timestamp),
      agent: entry.agent,
      action: entry.action,
      detail: entry.detail,
    })),
    hasEngineResult: detail.has_engine_result,
    hasValidationReport: detail.has_validation_report,
    engineResult: previous?.engineResult ?? null,
    validationReport: previous?.validationReport ?? null,
  };
}

export function getModule(
  engineResult: AnalysisDetail["engineResult"],
  moduleName: string,
) {
  return engineResult?.modules.find((module) => module.module_name === moduleName) ?? null;
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(1);
}

export function formatMetricValue(value: number | string | null | undefined): string {
  if (value == null || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(value);
}
