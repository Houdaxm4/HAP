import type {
  AnalysisDetail,
  NewAnalysisFormData,
  PipelineOutputs,
  PipelineStage,
} from "./types";
import type { BackendAnalysis } from "./api";
import {
  PENDING_OUTPUTS,
  PIPELINE_PENDING_MESSAGE,
  progressForStage,
  statusForStage,
} from "./pipeline-stages";
import { getAnalystLabel } from "./app_config";

function typeLabel(type: NewAnalysisFormData["analysisType"]): string {
  const labels = {
    new_company: "New Company Initiation",
    annual_update: "Annual Update",
    quarterly_update: "Quarterly Update",
  };
  return labels[type];
}

export function createLocalAnalysis(data: NewAnalysisFormData): AnalysisDetail {
  const id = data.ticker.toLowerCase();
  const now = new Date().toISOString();

  return {
    id,
    backendAnalysisId: null,
    backendConnected: false,
    isDemo: false,
    company: data.companyName,
    ticker: data.ticker.toUpperCase(),
    type: typeLabel(data.analysisType),
    status: "Queued",
    progress: 0,
    pipelineStage: "created",
    pipelineMessage:
      "Files recorded locally. Connect the HAP backend to run the real pipeline.",
    pipelineOutputs: { ...PENDING_OUTPUTS },
    startedAt: now,
    analyst: getAnalystLabel(),
    sector: "Pending identification",
    marketCap: "—",
    thesis: data.notes || "Awaiting workbook completion from the real analysis pipeline.",
    priceTarget: "—",
    rating: "Pending",
    keyMetrics: [],
    workbookSheets: data.prefilledWorkbook
      ? [
          {
            name: data.prefilledWorkbook.name,
            rows: 0,
            lastUpdated: "Uploaded",
            status: "pending",
          },
        ]
      : [],
    verificationChecks: [],
    decisionLog: [
      {
        id: `d-${Date.now()}`,
        timestamp: new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        agent: "Orchestrator",
        action: "Run created",
        detail: `${typeLabel(data.analysisType)} for ${data.ticker.toUpperCase()} awaiting backend pipeline.`,
      },
    ],
    executiveSummary: PIPELINE_PENDING_MESSAGE,
    chatHistory: [
      {
        id: `c-${Date.now()}`,
        role: "assistant",
        content: `Created ${typeLabel(data.analysisType)} for ${data.companyName} (${data.ticker.toUpperCase()}). ${PIPELINE_PENDING_MESSAGE}`,
        timestamp: new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      },
    ],
    uploadedFiles: {
      prefilledWorkbook: data.prefilledWorkbook?.name ?? null,
      previousWorkbook: data.previousWorkbook?.name ?? null,
      customRunFilter: data.customRunFilter?.name ?? null,
    },
  };
}

export function mapBackendAnalysis(
  backend: BackendAnalysis,
  form?: NewAnalysisFormData,
): AnalysisDetail {
  const stage = backend.pipeline.current_stage as PipelineStage;
  const outputs = backend.pipeline.outputs as PipelineOutputs;

  return {
    id: backend.ticker.toLowerCase(),
    backendAnalysisId: backend.analysis_id,
    backendConnected: true,
    isDemo: false,
    company: backend.company,
    ticker: backend.ticker,
    type: backend.analysis_type,
    status: statusForStage(stage),
    progress: progressForStage(stage),
    pipelineStage: stage,
    pipelineMessage: backend.pipeline.message,
    pipelineOutputs: outputs,
    startedAt: backend.created_at,
    analyst: getAnalystLabel(),
    sector: "Pending identification",
    marketCap: "—",
    thesis:
      form?.notes ||
      "Workbook completion and investment analysis will run after backend pipeline stages finish.",
    priceTarget: "—",
    rating: "Pending",
    keyMetrics: [],
    workbookSheets: backend.files.prefilled_workbook
      ? [
          {
            name: backend.files.prefilled_workbook.filename,
            rows: 0,
            lastUpdated: "Uploaded",
            status: "pending",
          },
        ]
      : [],
    verificationChecks: [],
    decisionLog: [
      {
        id: `d-${backend.analysis_id}-created`,
        timestamp: new Date(backend.created_at).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        agent: "Orchestrator",
        action: "Backend run created",
        detail: `${backend.ticker} registered with HAP backend.`,
      },
    ],
    executiveSummary: backend.pipeline.message,
    chatHistory: [
      {
        id: `c-${backend.analysis_id}-created`,
        role: "assistant",
        content: `${backend.company} (${backend.ticker}) is at stage: ${stage}. ${backend.pipeline.message}`,
        timestamp: new Date(backend.updated_at).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      },
    ],
    uploadedFiles: {
      prefilledWorkbook: backend.files.prefilled_workbook?.filename ?? null,
      previousWorkbook: backend.files.previous_workbook?.filename ?? null,
      customRunFilter: backend.files.custom_run_filter?.filename ?? null,
    },
  };
}

export function syncAnalysisFromBackend(
  analysis: AnalysisDetail,
  backend: BackendAnalysis,
): AnalysisDetail {
  const stage = backend.pipeline.current_stage as PipelineStage;
  const outputs = backend.pipeline.outputs as PipelineOutputs;

  return {
    ...analysis,
    backendAnalysisId: backend.analysis_id,
    backendConnected: true,
    status: statusForStage(stage),
    progress: progressForStage(stage),
    pipelineStage: stage,
    pipelineMessage: backend.pipeline.message,
    pipelineOutputs: outputs,
    executiveSummary:
      stage === "outputs_ready"
        ? "Pipeline outputs are ready for review."
        : backend.pipeline.message,
  };
}

export function isAnalysisComplete(analysis: AnalysisDetail): boolean {
  return analysis.pipelineStage === "outputs_ready";
}

export function hasRealOutputs(analysis: AnalysisDetail): boolean {
  return Object.values(analysis.pipelineOutputs).every((status) => status === "ready");
}
