export type NewAnalysisType = "new_company" | "annual_update" | "quarterly_update";

export type DisplayStatus =
  | "Created"
  | "Uploaded"
  | "Processing"
  | "Waiting for filing collection"
  | "Failed"
  | "Complete";

export interface NewAnalysisFormData {
  companyName: string;
  ticker: string;
  analysisType: NewAnalysisType;
  prefilledWorkbook: File | null;
  previousWorkbook: File | null;
  customRunFilter: File | null;
  notes: string;
}

export interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  content: string;
  timestamp: string;
}

export interface PipelineOutputs {
  completed_workbook?: string | null;
  provenance_report?: string | null;
  discrepancy_report?: string | null;
  validation_report?: string | null;
  sec_filings_manifest?: string | null;
  workbook_structure?: string | null;
  custom_run_mapping?: string | null;
}

export interface BackendDecisionLogEntry {
  agent: string;
  action: string;
  detail: string;
  timestamp: string;
  confidence?: number | null;
  citations?: string[];
}

export interface BackendPipelineStatus {
  state: "idle" | "processing" | "waiting" | "complete" | "failed";
  current_stage: string | null;
  stages_completed: string[];
  progress_pct: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  outputs: PipelineOutputs;
}

export interface UploadedFileInfo {
  filename: string;
  stored_filename: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface BackendAnalysisResponse {
  analysis_id: string;
  company: string;
  ticker: string;
  analysis_type: string;
  status: string;
  display_status: DisplayStatus;
  created_at: string;
  updated_at: string;
  cik?: string | null;
  pipeline: BackendPipelineStatus;
  decision_log: BackendDecisionLogEntry[];
  files: {
    prefilled_workbook?: UploadedFileInfo | null;
    previous_workbook?: UploadedFileInfo | null;
    custom_run_filter?: UploadedFileInfo | null;
  };
}

export interface DecisionLogEntry {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
  detail: string;
  confidence?: number | null;
  citations?: string[];
}

export interface AnalysisRecord {
  id: string;
  company: string;
  ticker: string;
  type: string;
  displayStatus: DisplayStatus;
  progress: number;
  currentStage: string | null;
  stagesCompleted: string[];
  pipelineState: string;
  pipelineError: string | null;
  startedAt: string;
  updatedAt: string;
  createdAt: string;
  outputs: PipelineOutputs;
  decisionLog: DecisionLogEntry[];
  files: BackendAnalysisResponse["files"];
  notes: string;
  // Detail-tab placeholders until later milestones fill them.
  sector: string;
  marketCap: string;
  thesis: string;
  priceTarget: string;
  rating: string;
  keyMetrics: { label: string; value: string; change?: string }[];
  workbookSheets: {
    name: string;
    rows: number;
    lastUpdated: string;
    status: "synced" | "pending" | "error";
  }[];
  verificationChecks: {
    id: string;
    label: string;
    status: "pass" | "warn" | "pending";
    detail: string;
  }[];
  executiveSummary: string;
  chatHistory: ChatMessage[];
}

/** @deprecated Prefer AnalysisRecord — kept for existing tab imports */
export type AnalysisDetail = AnalysisRecord;

/** @deprecated Legacy mock status union */
export type AnalysisStatus = DisplayStatus;
