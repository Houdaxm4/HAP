import type {
  AnalysisRecord,
  BackendAnalysisResponse,
  CellProvenance,
  NewAnalysisFormData,
  ValidationReport,
  WorkbookStructure,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_HAP_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string | { msg?: string }[] };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
        detail = payload.detail[0].msg;
      }
    } catch {
      // Keep default detail when response is not JSON.
    }
    throw new ApiError(detail || `Request failed (${response.status})`, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

const ANALYSIS_TYPE_LABELS: Record<NewAnalysisFormData["analysisType"], string> = {
  new_company: "New Company",
  annual_update: "Annual Update",
  quarterly_update: "Quarterly Update",
};

export function mapBackendAnalysis(data: BackendAnalysisResponse): AnalysisRecord {
  return {
    id: data.analysis_id,
    company: data.company,
    ticker: data.ticker,
    type: data.analysis_type,
    displayStatus: data.display_status,
    progress: data.pipeline?.progress_pct ?? 0,
    currentStage: data.pipeline?.current_stage ?? null,
    stagesCompleted: data.pipeline?.stages_completed ?? [],
    pipelineState: data.pipeline?.state ?? "idle",
    pipelineError: data.pipeline?.error ?? null,
    startedAt: data.pipeline?.started_at ?? data.created_at,
    updatedAt: data.updated_at,
    createdAt: data.created_at,
    outputs: data.pipeline?.outputs ?? {},
    decisionLog: (data.decision_log ?? []).map((entry, index) => ({
      id: `${data.analysis_id}-${index}`,
      agent: entry.agent,
      action: entry.action,
      detail: entry.detail,
      timestamp: entry.timestamp,
      confidence: entry.confidence,
      citations: entry.citations ?? [],
    })),
    files: data.files ?? {},
    notes: "",
  };
}

export function getApiBaseUrl(): string {
  return API_BASE;
}

export function artifactUrl(analysisId: string, artifactName: string): string {
  return `${API_BASE}/analysis/${analysisId}/outputs/${artifactName}`;
}

export function provenanceUrl(analysisId: string, worksheet: string, cell: string): string {
  const cellRef = `${worksheet}!${cell.toUpperCase()}`;
  return `${API_BASE}/analysis/${analysisId}/provenance/${encodeURIComponent(cellRef)}`;
}

export async function checkArtifactExists(
  analysisId: string,
  artifactName: string,
): Promise<boolean> {
  const response = await fetch(artifactUrl(analysisId, artifactName), { method: "HEAD" });
  return response.ok;
}

export async function listAnalyses(): Promise<AnalysisRecord[]> {
  const payload = await request<BackendAnalysisResponse[]>("/analysis");
  return payload.map(mapBackendAnalysis);
}

export async function getAnalysis(analysisId: string): Promise<AnalysisRecord> {
  const payload = await request<BackendAnalysisResponse>(`/analysis/${analysisId}`);
  return mapBackendAnalysis(payload);
}

export async function createAnalysis(data: NewAnalysisFormData): Promise<string> {
  const payload = await request<{ analysis_id: string }>("/analysis/create", {
    method: "POST",
    body: JSON.stringify({
      company: data.companyName.trim(),
      ticker: data.ticker.trim().toUpperCase(),
      analysis_type: ANALYSIS_TYPE_LABELS[data.analysisType],
    }),
  });
  return payload.analysis_id;
}

export async function uploadAnalysisFiles(
  analysisId: string,
  data: NewAnalysisFormData,
): Promise<void> {
  const formData = new FormData();
  if (!data.prefilledWorkbook) {
    throw new ApiError("Prefilled workbook is required.", 400);
  }
  if (!data.customRunFilter) {
    throw new ApiError("custom_run_filter is required.", 400);
  }

  formData.append("prefilled_workbook", data.prefilledWorkbook);
  formData.append("custom_run_filter", data.customRunFilter);
  if (data.previousWorkbook) {
    formData.append("previous_workbook", data.previousWorkbook);
  }

  await request(`/analysis/${analysisId}/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function runAnalysisPipeline(analysisId: string): Promise<void> {
  await request(`/analysis/${analysisId}/run`, { method: "POST" });
}

export async function startAnalysisWorkflow(data: NewAnalysisFormData): Promise<string> {
  const analysisId = await createAnalysis(data);
  await uploadAnalysisFiles(analysisId, data);
  await runAnalysisPipeline(analysisId);
  return analysisId;
}

export async function fetchJsonArtifact<T>(analysisId: string, artifactName: string): Promise<T> {
  return request<T>(`/analysis/${analysisId}/outputs/${artifactName}`);
}

export async function fetchCellProvenance(
  analysisId: string,
  worksheet: string,
  cell: string,
): Promise<CellProvenance> {
  const cellRef = `${worksheet}!${cell.toUpperCase()}`;
  return request<CellProvenance>(
    `/analysis/${analysisId}/provenance/${encodeURIComponent(cellRef)}`,
  );
}

export async function fetchValidationReport(analysisId: string): Promise<ValidationReport> {
  return fetchJsonArtifact<ValidationReport>(analysisId, "validation_report.json");
}

export async function fetchWorkbookStructure(analysisId: string): Promise<WorkbookStructure> {
  return fetchJsonArtifact<WorkbookStructure>(analysisId, "workbook_structure.json");
}
