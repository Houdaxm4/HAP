import { APP_CONFIG } from "./app_config";

export type CreateAnalysisPayload = {
  company: string;
  ticker: string;
  analysis_type: string;
};

export type CreateAnalysisResult = {
  analysis_id: string;
  status: "created";
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function createAnalysis(
  payload: CreateAnalysisPayload,
): Promise<CreateAnalysisResult> {
  const response = await fetch(`${APP_CONFIG.backendBaseUrl}/analysis/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(
      detail || `Failed to create analysis (${response.status})`,
      response.status,
    );
  }

  return response.json() as Promise<CreateAnalysisResult>;
}
