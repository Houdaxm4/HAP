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
    public readonly url: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Backend route: POST /analysis/create (no /api prefix). */
export const ANALYSIS_CREATE_PATH = "/analysis/create";

export function getAnalysisCreateUrl(): string {
  const base = APP_CONFIG.backendBaseUrl.replace(/\/+$/, "").replace(/\/api$/, "");
  return new URL(ANALYSIS_CREATE_PATH, `${base}/`).href;
}

export async function createAnalysis(
  payload: CreateAnalysisPayload,
): Promise<CreateAnalysisResult> {
  const url = getAnalysisCreateUrl();

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(
      detail || `Failed to create analysis (${response.status})`,
      response.status,
      url,
    );
  }

  return response.json() as Promise<CreateAnalysisResult>;
}
