import type { AnalysisDetailDto, AnalysisSummary } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type CreateAnalysisPayload = {
  company: string;
  ticker: string;
  analysis_type: string;
};

export type CreateAnalysisResponse = {
  analysis_id: string;
  status: "created";
};

export type UploadAnalysisFilesPayload = {
  prefilledWorkbook: File;
  previousWorkbook?: File | null;
  customRunFilter?: File | null;
};

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `Request failed with status ${response.status}`;
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) =>
          typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item),
        )
        .join("; ");
    }
    return text;
  } catch {
    return text;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return response.json() as Promise<T>;
}

export function getApiBaseUrl(): string {
  return API_BASE;
}

export async function listAnalyses(): Promise<AnalysisSummary[]> {
  return requestJson<AnalysisSummary[]>("/analyses");
}

export async function getAnalysis(analysisId: string): Promise<AnalysisDetailDto> {
  return requestJson<AnalysisDetailDto>(`/analysis/${analysisId}`);
}

export async function createAnalysis(
  payload: CreateAnalysisPayload,
): Promise<CreateAnalysisResponse> {
  return requestJson<CreateAnalysisResponse>("/analysis/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company: payload.company.trim(),
      ticker: payload.ticker.trim().toUpperCase(),
      analysis_type: payload.analysis_type,
    }),
  });
}

export async function uploadAnalysisFiles(
  analysisId: string,
  files: UploadAnalysisFilesPayload,
): Promise<Record<string, unknown>> {
  const formData = new FormData();
  formData.append("prefilled_workbook", files.prefilledWorkbook);
  if (files.previousWorkbook) {
    formData.append("previous_workbook", files.previousWorkbook);
  }
  if (files.customRunFilter) {
    formData.append("custom_run_filter", files.customRunFilter);
  }

  const response = await fetch(`${API_BASE}/analysis/${analysisId}/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return response.json() as Promise<Record<string, unknown>>;
}

export async function runAnalysis(analysisId: string): Promise<{
  analysis_id: string;
  status: string;
  message: string;
}> {
  return requestJson(`/analysis/${analysisId}/run`, {
    method: "POST",
  });
}

export async function getAnalysisOutputJson<T>(
  analysisId: string,
  artifactName: string,
): Promise<T | null> {
  const response = await fetch(
    `${API_BASE}/analysis/${analysisId}/outputs/${encodeURIComponent(artifactName)}`,
  );
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return response.json() as Promise<T>;
}

export type OutputArtifactDto = {
  name: string;
  size_bytes: number;
  download_path: string;
};

export async function listAnalysisOutputs(
  analysisId: string,
): Promise<OutputArtifactDto[]> {
  const payload = await requestJson<{
    analysis_id: string;
    artifacts: OutputArtifactDto[];
  }>(`/analysis/${analysisId}/outputs`);
  return payload.artifacts;
}

export function getOutputDownloadUrl(
  analysisId: string,
  artifactName: string,
): string {
  return `${API_BASE}/analysis/${analysisId}/outputs/${encodeURIComponent(artifactName)}`;
}

export function isAnalysisTerminal(detail: {
  pipeline_state: string;
  is_complete: boolean;
  status: string;
}): boolean {
  return (
    detail.is_complete ||
    detail.pipeline_state === "complete" ||
    detail.pipeline_state === "failed" ||
    detail.status === "failed"
  );
}
