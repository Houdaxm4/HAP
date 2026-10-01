import type { AnalysisDetailDto, AnalysisSummary } from "./types";

function resolveApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  const fallback = "http://127.0.0.1:8000";
  const base = (configured && configured.length > 0 ? configured : fallback).replace(
    /\/+$/,
    "",
  );
  return base;
}

const API_BASE = resolveApiBaseUrl();

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
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: init?.headers,
  });
  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/me") {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("hap:unauthorized"));
    }
  }
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return response.json() as Promise<T>;
}

export type AuthMeResponse = {
  authenticated: boolean;
  auth_required: boolean;
  username: string | null;
};

export async function fetchAuthMe(): Promise<AuthMeResponse> {
  return requestJson<AuthMeResponse>("/auth/me");
}

export async function loginWithPassword(username: string, password: string): Promise<void> {
  await requestJson("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export async function logoutSession(): Promise<void> {
  await requestJson("/auth/logout", { method: "POST" });
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
    credentials: "include",
  });
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("hap:unauthorized"));
  }
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
    { credentials: "include" },
  );
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("hap:unauthorized"));
  }
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

export async function reviewLeaseRate(
  analysisId: string,
  payload: { action: "approve" | "correct" | "request_more_evidence"; rate?: number; reason?: string },
): Promise<Record<string, unknown>> {
  return requestJson(`/analysis/${analysisId}/analyst-review/lease-rate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function overrideRdUsefulLife(
  analysisId: string,
  payload: { useful_life: number; reason?: string },
): Promise<Record<string, unknown>> {
  return requestJson(`/analysis/${analysisId}/analyst-review/rd-useful-life`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getAnalystReview(analysisId: string): Promise<{
  analysis_id: string;
  lease_rate_review: Record<string, unknown> | null;
  rd_useful_life_decision: Record<string, unknown> | null;
  run_state: Record<string, unknown> | null;
}> {
  return requestJson(`/analysis/${analysisId}/analyst-review`);
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
    detail.status === "failed" ||
    detail.status === "awaiting_analyst_review" ||
    detail.status === "needs_review" ||
    (detail.pipeline_state === "complete" && detail.status === "complete") ||
    detail.pipeline_state === "failed"
  );
}

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatReplyDto = {
  reply: string;
  tool_calls: { name: string; input: Record<string, unknown>; ok: boolean }[];
  iterations: number;
  stop_reason: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  budget?: BudgetStatus | null;
  source: "built_in" | "cache" | "claude" | "none";
  intent?: string | null;
  needs_claude: boolean;
  estimated_cost_usd?: number | null;
};

export type ChatMode = "auto" | "free" | "claude";

/** Ask the read-only HAP Analyst agent about one analysis. */
export async function chatWithAnalyst(
  analysisId: string,
  messages: ChatTurn[],
  mode: ChatMode = "auto",
): Promise<ChatReplyDto> {
  return requestJson<ChatReplyDto>(`/analysis/${analysisId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, mode }),
  });
}

export type BudgetStatus = {
  month: string;
  spent_usd: number;
  cap_usd: number;
  remaining_usd: number;
  percent_used: number;
  level: "ok" | "warning" | "exceeded";
};

export async function getBudget(): Promise<BudgetStatus> {
  return requestJson<BudgetStatus>("/budget");
}

export type FeedbackPayload = {
  target: string;
  action:
    | "approve"
    | "correct"
    | "reject"
    | "request_more_evidence"
    | "thumbs_up"
    | "thumbs_down"
    | "comment";
  agent_value?: unknown;
  analyst_value?: unknown;
  reason?: string;
  context?: Record<string, unknown>;
};

/** Tell HAP what you decided about something the agent proposed or said. */
export async function submitFeedback(
  analysisId: string,
  payload: FeedbackPayload,
): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/analysis/${analysisId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export type Lesson = {
  id: string;
  created_at: string;
  status: "proposed" | "approved" | "rejected" | "retired";
  kind: string;
  target: string;
  analysis_type: string;
  title: string;
  text: string;
  evidence: string[];
  support_count: number;
  decided_at: string | null;
  decision_note: string | null;
};

export async function listLessons(status?: Lesson["status"]): Promise<Lesson[]> {
  const query = status ? `?status=${status}` : "";
  return (await requestJson<{ items: Lesson[] }>(`/lessons${query}`)).items;
}

/** Look for repeated corrections in your feedback and propose lessons (free). */
export async function proposeLessons(): Promise<{ created: Lesson[]; count: number }> {
  return requestJson("/lessons/propose", { method: "POST" });
}

async function lessonAction(
  id: string,
  action: "approve" | "reject" | "retire",
  body: { text?: string; note?: string } = {},
): Promise<Lesson> {
  return requestJson<Lesson>(`/lessons/${id}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const approveLesson = (id: string, body?: { text?: string; note?: string }) =>
  lessonAction(id, "approve", body);
export const rejectLesson = (id: string, body?: { note?: string }) => lessonAction(id, "reject", body);
export const retireLesson = (id: string, body?: { note?: string }) => lessonAction(id, "retire", body);

export type RecommendationConflict = {
  available: boolean;
  conflict: boolean;
  headline: string | null;
  headline_source: string;
  final_recommendation: string | null;
  engine_recommendation: string | null;
  message: string | null;
};

export async function getRecommendationConflict(analysisId: string): Promise<RecommendationConflict> {
  return requestJson<RecommendationConflict>(`/analysis/${encodeURIComponent(analysisId)}/recommendation-conflict`);
}

export type AgentCheckpoint = {
  id: string;
  kind: string;
  status: "open" | "answered";
  title: string;
  summary: string;
  options: string[];
  created_at: string;
  answer: { decision: string; note: string; at: string } | null;
};

export type AgentRunState = {
  analysis_id: string;
  phase: "not_started" | "pipeline" | "waiting_for_you" | "revising" | "done" | "stopped";
  checkpoints: AgentCheckpoint[];
  history: { at: string; event: string }[];
};

export type AgentDossier = {
  company: string;
  ticker: string;
  headline: RecommendationConflict;
  flags: string[];
  outside_evidence: {
    items: { kind: string; source: string; url: string; as_of: string | null; reliability_note: string; title: string; content: string }[];
    errors: string[];
  };
  my_take: { text: string | null; label?: string; error?: string } | null;
  note: string;
};

const jsonPost = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const getAgentRun = (id: string) => requestJson<AgentRunState>(`/analysis/${encodeURIComponent(id)}/agent`);
export const startAgentRun = (id: string, withTake: boolean) =>
  requestJson<AgentRunState>(`/analysis/${encodeURIComponent(id)}/agent/run?with_take=${withTake}`, jsonPost());
export const continueAgentRun = (id: string, withTake: boolean) =>
  requestJson<Record<string, unknown>>(`/analysis/${encodeURIComponent(id)}/agent/continue?with_take=${withTake}`, jsonPost());
export const getAgentDossier = (id: string) => requestJson<AgentDossier>(`/analysis/${encodeURIComponent(id)}/agent/dossier`);
export const answerCheckpoint = (id: string, checkpointId: string, decision: "approve" | "revise" | "stop", note?: string) =>
  requestJson<AgentRunState>(
    `/analysis/${encodeURIComponent(id)}/agent/checkpoints/${encodeURIComponent(checkpointId)}`,
    jsonPost({ decision, note }),
  );
