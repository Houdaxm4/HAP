export type NewAnalysisType = "new_company" | "annual_update" | "quarterly_update";

export type DisplayStatus =
  | "Complete"
  | "Processing"
  | "Waiting for backend pipeline."
  | "Failed";

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
  state: "idle" | "processing" | "complete" | "failed";
  current_stage: string | null;
  stages_completed: string[];
  progress_pct: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  outputs: PipelineOutputs;
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

export interface UploadedFileInfo {
  filename: string;
  stored_filename: string;
  size_bytes: number;
  uploaded_at: string;
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
}

/** @deprecated Use AnalysisRecord — kept for gradual tab migration */
export type AnalysisDetail = AnalysisRecord;

export interface CellProvenance {
  cell_ref: string;
  worksheet: string;
  cell: string;
  concept: string;
  period: string;
  value?: number | string | null;
  status: string;
  source_document?: string | null;
  filing_type?: string | null;
  filing_year?: number | null;
  filing_date?: string | null;
  accession_number?: string | null;
  page?: number | null;
  xbrl_tag?: string | null;
  confidence?: number | null;
  reasoning?: string | null;
  failure_reason?: string | null;
}

export interface ValidationCheck {
  cell_ref: string;
  worksheet: string;
  cell: string;
  concept: string;
  period: string;
  check_type: string;
  status: "pass" | "warn" | "fail";
  expected_value?: number | string | null;
  actual_value?: number | string | null;
  message: string;
  source_document?: string | null;
  xbrl_tag?: string | null;
}

export interface ValidationReport {
  analysis_id: string;
  ticker: string;
  checks: ValidationCheck[];
  pass_count: number;
  warn_count: number;
  fail_count: number;
  summary: string;
}

export interface WorkbookStructure {
  workbook_filename: string;
  worksheet_names: string[];
  visible_sheets: string[];
  hidden_sheets: string[];
  formula_count: number;
  non_empty_cell_count: number;
}

export interface WorkbookSheetRow {
  name: string;
  visibility: "visible" | "hidden";
  formulaCount?: number;
  valueCount?: number;
}

export interface VerificationCheckRow {
  id: string;
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}
