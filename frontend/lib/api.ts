export const API_BASE_URL =
  process.env.NEXT_PUBLIC_HAP_API_URL ?? "http://127.0.0.1:8000";

export type BackendPipelineStage =
  | "created"
  | "template_uploaded"
  | "filing_collection"
  | "workbook_completion"
  | "workbook_validation"
  | "fundamental_analysis"
  | "market_valuation_analysis"
  | "final_recommendation"
  | "outputs_ready"
  | "failed";

export type BackendOutputStatus = "pending" | "ready" | "unavailable";

export type BackendPipelineState = {
  current_stage: BackendPipelineStage;
  stage_status: "pending" | "in_progress" | "not_implemented" | "complete" | "failed";
  message: string;
  outputs: {
    workbook: BackendOutputStatus;
    investment_memo: BackendOutputStatus;
    source_citations: BackendOutputStatus;
    discrepancy_report: BackendOutputStatus;
    verification_report: BackendOutputStatus;
  };
  updated_at: string;
};

export type BackendAnalysis = {
  analysis_id: string;
  company: string;
  ticker: string;
  analysis_type: string;
  status: string;
  created_at: string;
  updated_at: string;
  files: {
    prefilled_workbook?: { filename: string; size_bytes: number; uploaded_at: string };
    previous_workbook?: { filename: string; size_bytes: number; uploaded_at: string };
    custom_run_filter?: { filename: string; size_bytes: number; uploaded_at: string };
  };
  pipeline: BackendPipelineState;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

export async function createBackendAnalysis(input: {
  company: string;
  ticker: string;
  analysisType: string;
}): Promise<BackendAnalysis> {
  const created = await request<{ analysis_id: string }>("/analysis/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company: input.company,
      ticker: input.ticker,
      analysis_type: input.analysisType,
    }),
  });

  return getBackendAnalysis(created.analysis_id);
}

export async function uploadBackendAnalysisFiles(
  analysisId: string,
  files: {
    prefilledWorkbook: File;
    customRunFilter: File;
    previousWorkbook?: File | null;
  },
): Promise<BackendAnalysis> {
  const formData = new FormData();
  formData.append("prefilled_workbook", files.prefilledWorkbook);
  formData.append("custom_run_filter", files.customRunFilter);
  if (files.previousWorkbook) {
    formData.append("previous_workbook", files.previousWorkbook);
  }

  await request<BackendAnalysis>(`/analysis/${analysisId}/upload`, {
    method: "POST",
    body: formData,
  });

  return getBackendAnalysis(analysisId);
}

export async function startBackendPipeline(analysisId: string): Promise<BackendPipelineState> {
  return request<BackendPipelineState>(`/analysis/${analysisId}/pipeline/start`, {
    method: "POST",
  });
}

export async function getBackendAnalysis(analysisId: string): Promise<BackendAnalysis> {
  return request<BackendAnalysis>(`/analysis/${analysisId}`);
}

export async function getBackendPipeline(analysisId: string): Promise<BackendPipelineState> {
  return request<BackendPipelineState>(`/analysis/${analysisId}/pipeline`);
}
