export type NewAnalysisType = "new_company" | "annual_update" | "quarterly_update";

export type DisplayStatus =
  | "Created"
  | "Uploaded"
  | "Processing"
  | "Waiting for filing collection"
  | "Filings collected"
  | "Statements extracted"
  | "Failed"
  | "Validation failed"
  | "Complete"
  | "Complete with warnings";

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
  custom_run_validation_report?: string | null;
  financial_statements?: string | null;
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
  validation_status?: "passed" | "passed_with_warnings" | "failed" | null;
  critical_issue_count?: number;
  warning_issue_count?: number;
  informational_issue_count?: number;
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

export interface CellFormatting {
  number_format?: string | null;
  font_name?: string | null;
  font_size?: number | null;
  font_bold?: boolean | null;
  font_italic?: boolean | null;
  font_color?: string | null;
  fill_pattern?: string | null;
  fill_color?: string | null;
  horizontal_alignment?: string | null;
  vertical_alignment?: string | null;
  wrap_text?: boolean | null;
  locked?: boolean | null;
}

export interface WorkbookCellInfo {
  address: string;
  row?: number | null;
  column?: number | null;
  value?: string | number | boolean | null;
  data_type: "formula" | "value" | "blank";
  formula?: string | null;
  is_formula: boolean;
  is_editable: boolean;
  formatting?: CellFormatting | null;
}

export interface WorkbookNamedRange {
  name: string;
  destinations: string[];
  attr_text?: string | null;
}

export interface WorkbookSheetInfo {
  name: string;
  visibility: "visible" | "hidden" | "veryHidden";
  index: number;
  dimensions?: string | null;
  max_row?: number | null;
  max_column?: number | null;
  formula_count: number;
  editable_cell_count: number;
  value_count: number;
  blank_count: number;
  non_empty_cell_count: number;
  formula_cells: WorkbookCellInfo[];
  editable_cells: WorkbookCellInfo[];
  cells: WorkbookCellInfo[];
}

export interface WorkbookMetadata {
  title?: string | null;
  subject?: string | null;
  creator?: string | null;
  description?: string | null;
  keywords?: string | null;
  category?: string | null;
  last_modified_by?: string | null;
  created?: string | null;
  modified?: string | null;
  content_status?: string | null;
  revision?: string | null;
  excel_base_date?: string | null;
  sheet_count: number;
  defined_name_count: number;
}

export interface WorkbookStructure {
  workbook_filename: string;
  metadata: WorkbookMetadata;
  worksheet_names: string[];
  visible_sheets: string[];
  hidden_sheets: string[];
  named_ranges: WorkbookNamedRange[];
  worksheets: WorkbookSheetInfo[];
  formula_count: number;
  editable_cell_count: number;
  non_empty_cell_count: number;
  formula_cells: string[];
  editable_cells: string[];
}

export type CustomRunCheckType =
  | "required_columns"
  | "ticker"
  | "fiscal_dates"
  | "quarter_sequence"
  | "duplicate_periods"
  | "missing_quarters"
  | "numeric_consistency"
  | "workbook_reference";

export interface CustomRunValidationIssue {
  check_type: CustomRunCheckType;
  status: "pass" | "warn" | "fail";
  message: string;
  row_number?: number | null;
  concept?: string | null;
  period?: string | null;
  cell_ref?: string | null;
  details?: Record<string, unknown>;
}

export interface CustomRunValidationReport {
  analysis_id: string;
  ticker: string;
  source_filename: string;
  entry_count: number;
  columns_found: string[];
  checks: CustomRunValidationIssue[];
  pass_count: number;
  warn_count: number;
  fail_count: number;
  is_valid: boolean;
  summary: string;
}

/** @deprecated Prefer AnalysisRecord — kept for existing tab imports */
export type AnalysisDetail = AnalysisRecord;

/** @deprecated Legacy mock status union */
export type AnalysisStatus = DisplayStatus;
