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

function buildFromPhase1(backend: BackendAnalysis) {
  const phase1 = backend.phase1;
  if (!phase1) {
    return {
      workbookSheets: backend.files.prefilled_workbook
        ? [
            {
              name: backend.files.prefilled_workbook.filename,
              rows: 0,
              lastUpdated: "Uploaded",
              status: "pending" as const,
            },
          ]
        : [],
      verificationChecks: [],
      keyMetrics: [],
      decisionLog: [],
    };
  }

  return {
    workbookSheets: [
      {
        name: "Completed workbook",
        rows: phase1.fills_applied.length,
        lastUpdated: "Phase 1",
        status: phase1.validation_passed ? ("synced" as const) : ("pending" as const),
      },
    ],
    verificationChecks: [
      {
        id: `v-${backend.analysis_id}-phase1`,
        label: "SEC-backed workbook fills",
        status: phase1.validation_passed ? ("pass" as const) : ("warn" as const),
        detail: phase1.validation_message,
      },
    ],
    keyMetrics: [
      { label: "Resolved ticker", value: phase1.resolved_ticker },
      { label: "SEC filings", value: String(phase1.filings.length) },
      { label: "Cells filled", value: String(phase1.fills_applied.length) },
    ],
    decisionLog: [
      {
        id: `d-${backend.analysis_id}-phase1`,
        timestamp: new Date(backend.updated_at).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        agent: "Phase 1",
        action: "Workbook filled from SEC facts",
        detail: phase1.validation_message,
      },
    ],
  };
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
    decisionLog: [],
    executiveSummary: PIPELINE_PENDING_MESSAGE,
    chatHistory: [
      {
        id: `c-${Date.now()}`,
        role: "assistant",
        content: `Created ${typeLabel(data.analysisType)} for ${data.companyName} (${data.ticker.toUpperCase()}). Start the HAP backend to run Phase 1.`,
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
  const phase1View = buildFromPhase1(backend);

  return {
    id: backend.ticker.toLowerCase(),
    backendAnalysisId: backend.analysis_id,
    backendConnected: true,
    isDemo: false,
    company: backend.company,
    ticker: backend.ticker,
    type: backend.analysis_type,
    status: statusForStage(stage, backend.status),
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
    keyMetrics: phase1View.keyMetrics,
    workbookSheets: phase1View.workbookSheets,
    verificationChecks: phase1View.verificationChecks,
    decisionLog: phase1View.decisionLog,
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
  const phase1View = buildFromPhase1(backend);

  return {
    ...analysis,
    company: backend.company,
    ticker: backend.ticker,
    backendAnalysisId: backend.analysis_id,
    backendConnected: true,
    status: statusForStage(stage, backend.status),
    progress: progressForStage(stage),
    pipelineStage: stage,
    pipelineMessage: backend.pipeline.message,
    pipelineOutputs: outputs,
    keyMetrics: phase1View.keyMetrics.length ? phase1View.keyMetrics : analysis.keyMetrics,
    workbookSheets: phase1View.workbookSheets.length
      ? phase1View.workbookSheets
      : analysis.workbookSheets,
    verificationChecks: phase1View.verificationChecks.length
      ? phase1View.verificationChecks
      : analysis.verificationChecks,
    decisionLog: [...analysis.decisionLog, ...phase1View.decisionLog],
    executiveSummary: backend.pipeline.message,
  };
}

export function isAnalysisComplete(analysis: AnalysisDetail): boolean {
  return analysis.pipelineStage === "outputs_ready";
}

export function hasRealOutputs(analysis: AnalysisDetail): boolean {
  return analysis.pipelineOutputs.workbook === "ready";
}

export function isProcessing(analysis: AnalysisDetail): boolean {
  return analysis.status === "Processing";
}
