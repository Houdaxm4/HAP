import type { AnalysisDetail } from "./types";
import { getAnalystLabel } from "./app_config";
import { PENDING_OUTPUTS, PIPELINE_PENDING_MESSAGE } from "./pipeline-stages";

const DEMO_BASE = {
  analyst: getAnalystLabel(),
  sector: "Demo fixture",
  marketCap: "—",
  thesis: "Illustrative UI fixture only. Not a real analysis run.",
  priceTarget: "—",
  rating: "Pending",
  keyMetrics: [],
  verificationChecks: [],
  decisionLog: [],
  executiveSummary: PIPELINE_PENDING_MESSAGE,
  chatHistory: [],
  uploadedFiles: {
    prefilledWorkbook: null,
    previousWorkbook: null,
    customRunFilter: null,
  },
} satisfies Partial<AnalysisDetail>;

export const MOCK_ANALYSES: AnalysisDetail[] = [
  {
    ...DEMO_BASE,
    id: "demo-ensg",
    backendAnalysisId: null,
    backendConnected: false,
    isDemo: true,
    company: "Demo — The Ensign Group",
    ticker: "ENSG",
    type: "New Company Initiation",
    status: "Running",
    progress: 14,
    pipelineStage: "template_uploaded",
    pipelineMessage:
      "Demo fixture showing the intended workflow after template upload. Real outputs are pending backend implementation.",
    pipelineOutputs: { ...PENDING_OUTPUTS },
    startedAt: "2026-07-08T00:00:00Z",
    workbookSheets: [
      {
        name: "Prefilled template (demo)",
        rows: 0,
        lastUpdated: "Demo",
        status: "pending",
      },
    ],
    chatHistory: [
      {
        id: "demo-ensg-1",
        role: "assistant",
        content:
          "This is a demo row illustrating the HAP pipeline. Upload ENSG through New Analysis to create a real run.",
        timestamp: "08:00 AM",
      },
    ],
  },
];
