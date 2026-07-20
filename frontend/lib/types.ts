export type AnalysisStatus = "Running" | "Queued" | "Review" | "Complete" | "Failed";

export type NewAnalysisType = "new_company" | "annual_update" | "quarterly_update";

export interface NewAnalysisFormData {
  companyName: string;
  ticker: string;
  analysisType: NewAnalysisType;
  prefilledWorkbook: File | null;
  previousWorkbook: File | null;
  customRunFilter: File | null;
  notes: string;
}

/** Mirrors backend AnalysisSummaryResponse. */
export type AnalysisSummary = {
  analysis_id: string;
  company: string;
  ticker: string;
  analysis_type: string;
  status: string;
  pipeline_state: "idle" | "processing" | "complete" | "failed";
  progress_pct: number;
  current_stage: string | null;
  pipeline_error: string | null;
  is_complete: boolean;
  created_at: string;
  updated_at: string;
  recommendation: string | null;
  recommendation_label: string | null;
  business_quality_score: number | null;
  investment_attractiveness_score: number | null;
};

/** Mirrors backend AnalysisDetailResponse. */
export type AnalysisDetailDto = AnalysisSummary & {
  files: Record<string, unknown>;
  pipeline: {
    state: "idle" | "processing" | "complete" | "failed";
    progress_pct: number;
    current_stage?: string | null;
    stages_completed?: string[];
    outputs?: Record<string, string | null>;
    error?: string | null;
  };
  decision_log: {
    agent: string;
    action: string;
    detail: string;
    timestamp: string;
  }[];
  cik: string | null;
  outputs: Record<string, string | null>;
  has_engine_result: boolean;
  has_validation_report: boolean;
};

export type EngineModuleResult = {
  module_name: string;
  module_version?: string;
  status: string;
  score?: number | null;
  confidence?: number;
  findings?: EngineFinding[];
  metrics?: EngineMetric[];
  risks?: EngineRisk[];
  opportunities?: EngineOpportunity[];
  component_scores?: { code: string; score: number; confidence?: number; name?: string; label?: string }[];
  coverage?: Record<string, unknown>;
  error?: string | null;
};

export type EngineFinding = {
  finding_id: string;
  code: string;
  rule_id?: string | null;
  severity: string;
  direction?: string;
  category: string;
  summary: string;
  confidence?: number;
};

export type EngineMetric = {
  code: string;
  name?: string;
  label?: string;
  value?: number | string | null;
  unit?: string | null;
  period?: string | null;
  confidence?: number;
};

export type EngineRisk = {
  risk_id: string;
  code: string;
  severity: string;
  summary: string;
  confidence?: number;
};

export type EngineOpportunity = {
  opportunity_id: string;
  code: string;
  summary: string;
  confidence?: number;
};

export type EngineAggregatorResult = {
  score?: number | null;
  confidence?: number;
  classification: string;
  classification_label: string;
  module_contributions?: {
    module_name: string;
    weight: number;
    effective_weight?: number;
    score?: number | null;
    confidence?: number;
    status: string;
  }[];
  strengths?: EngineFinding[];
  weaknesses?: EngineRisk[];
  opportunities?: EngineOpportunity[];
  skipped_modules?: string[];
  low_confidence_modules?: string[];
};

export type EngineRecommendation = {
  recommendation: string;
  recommendation_label: string;
  confidence?: number;
  business_quality_score?: number | null;
  investment_attractiveness_score?: number | null;
  business_quality_classification?: string;
  investment_attractiveness_classification?: string;
  reasons?: {
    reason_id: string;
    code: string;
    category: string;
    summary: string;
    confidence?: number;
  }[];
  strengths?: EngineFinding[];
  weaknesses?: EngineRisk[];
  opportunities?: EngineOpportunity[];
};

export type AnalysisEngineResult = {
  analysis_id: string;
  ticker: string;
  generated_at?: string;
  modules: EngineModuleResult[];
  findings?: EngineFinding[];
  metrics?: EngineMetric[];
  metric_comparisons?: {
    metric_code: string;
    workbook_value?: number | string | null;
    hap_value?: number | string | null;
    status?: string;
  }[];
  risks?: EngineRisk[];
  opportunities?: EngineOpportunity[];
  confidence?: number;
  summary_metrics?: Record<string, unknown>;
  business_quality?: EngineAggregatorResult | null;
  investment_attractiveness?: EngineAggregatorResult | null;
  recommendation?: EngineRecommendation | null;
};

export type ValidationReport = {
  analysis_id: string;
  ticker: string;
  checks: {
    cell_ref: string;
    worksheet: string;
    cell: string;
    concept: string;
    period: string;
    check_type: string;
    status: "pass" | "warn" | "fail";
    expected_value?: unknown;
    actual_value?: unknown;
    message: string;
  }[];
  pass_count: number;
  warn_count: number;
  fail_count: number;
  summary: string;
};

/** UI view model for pages — presentation fields only from Summary/Detail DTOs + artifacts. */
export interface AnalysisDetail {
  id: string;
  company: string;
  ticker: string;
  type: string;
  status: AnalysisStatus;
  progress: number;
  currentStage: string | null;
  pipelineError: string | null;
  startedAt: string;
  updatedAt: string;
  isComplete: boolean;
  recommendation: string | null;
  recommendationLabel: string | null;
  businessQualityScore: number | null;
  investmentAttractivenessScore: number | null;
  decisionLog: {
    id: string;
    timestamp: string;
    agent: string;
    action: string;
    detail: string;
  }[];
  outputs: Record<string, string | null>;
  hasEngineResult: boolean;
  hasValidationReport: boolean;
  engineResult: AnalysisEngineResult | null;
  validationReport: ValidationReport | null;
}

export type OutputArtifact = {
  name: string;
  size_bytes: number;
  download_path: string;
};
