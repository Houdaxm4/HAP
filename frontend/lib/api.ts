import type {
  AnalysisRecord,
  BackendAnalysisResponse,
  CustomRunValidationReport,
  NewAnalysisFormData,
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

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export function mapBackendAnalysis(data: BackendAnalysisResponse): AnalysisRecord {
  const stage = data.pipeline?.current_stage;
  const waiting = data.display_status === "Waiting for filing collection";

  return {
    id: data.analysis_id,
    company: data.company,
    ticker: data.ticker,
    type: data.analysis_type,
    displayStatus: data.display_status,
    progress: data.pipeline?.progress_pct ?? 0,
    currentStage: stage ?? null,
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
      timestamp: formatTimestamp(entry.timestamp),
      confidence: entry.confidence,
      citations: entry.citations ?? [],
    })),
    files: data.files ?? {},
    notes: "",
    sector: "Pending classification",
    marketCap: "—",
    thesis: waiting
      ? "Infrastructure pipeline complete. Waiting for SEC filing collection."
      : "Analysis initiated. Pipeline is processing uploaded workbooks.",
    priceTarget: "—",
    rating: "Pending",
    keyMetrics: [
      { label: "Stage", value: stage ?? "—" },
      { label: "Progress", value: `${data.pipeline?.progress_pct ?? 0}%` },
    ],
    workbookSheets: data.files?.prefilled_workbook
      ? [
          {
            name: data.files.prefilled_workbook.filename,
            rows: 0,
            lastUpdated: formatTimestamp(data.files.prefilled_workbook.uploaded_at),
            status: waiting ? "synced" : "pending",
          },
        ]
      : [],
    verificationChecks: waiting
      ? [
          {
            id: "infra-workbook",
            label: "Workbook parsed",
            status: "pass" as const,
            detail: "Prefilled workbook structure was parsed successfully.",
          },
          {
            id: "infra-custom-run",
            label: "custom_run_filter validated",
            status: "pass" as const,
            detail:
              "custom_run_filter validation report produced. Template was not populated.",
          },
          {
            id: "infra-filings",
            label: "Filing collection",
            status: "pending" as const,
            detail: "SEC filing collection is not implemented yet.",
          },
        ]
      : [],
    executiveSummary: waiting
      ? `${data.company} (${data.ticker}) infrastructure pipeline finished. Workbook and custom_run_filter are stored and validated. Filing collection has not started.`
      : `${data.company} (${data.ticker}) analysis is running through the infrastructure pipeline.`,
    chatHistory: [
      {
        id: `c-${data.analysis_id}`,
        role: "assistant",
        content: waiting
          ? `Infrastructure steps for ${data.ticker} are complete. Waiting for filing collection.`
          : `Tracking live pipeline progress for ${data.ticker}.`,
        timestamp: formatTimestamp(data.updated_at),
      },
    ],
  };
}

export function getApiBaseUrl(): string {
  return API_BASE;
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

export async function startAnalysisWorkflow(data: NewAnalysisFormData): Promise<string> {
  const analysisId = await createAnalysis(data);
  await uploadAnalysisFiles(analysisId, data);
  return analysisId;
}

export async function fetchWorkbookStructure(analysisId: string): Promise<WorkbookStructure> {
  return request<WorkbookStructure>(`/analysis/${analysisId}/workbook-structure`);
}

export async function fetchCustomRunValidation(
  analysisId: string,
): Promise<CustomRunValidationReport> {
  return request<CustomRunValidationReport>(`/analysis/${analysisId}/custom-run-validation`);
}
