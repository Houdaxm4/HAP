export type AnalysisStatus = "Running" | "Queued" | "Review" | "Complete";

export type NewAnalysisType = "new_company" | "annual_update" | "quarterly_update";

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

export interface AnalysisDetail {
  id: string;
  company: string;
  ticker: string;
  type: string;
  status: AnalysisStatus;
  progress: number;
  startedAt: string;
  analyst: string;
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
  decisionLog: {
    id: string;
    timestamp: string;
    agent: string;
    action: string;
    detail: string;
  }[];
  executiveSummary: string;
  chatHistory: ChatMessage[];
  completedAt?: string;
}

export type AnalysisType =
  | "New Company"
  | "Annual Update"
  | "Quarterly Update"
  | "DCF Valuation"
  | "Competitive Moat"
  | "Earnings Preview";

export type VerificationStatus = "pass" | "fail" | "warning" | "pending";

export type DecisionType = "data" | "model" | "assumption" | "override";

export interface Analysis {
  id: string;
  company: string;
  ticker: string;
  type: AnalysisType;
  status: AnalysisStatus;
  progress: number;
  startedAt: string;
  updatedAt: string;
  analyst: string;
  sector: string;
  marketCap: string;
  currentPrice: string;
  targetPrice: string;
  recommendation: "Buy" | "Hold" | "Sell" | "—";
  overview: {
    thesis: string;
    keyMetrics: { label: string; value: string; change?: string }[];
    timeline: { time: string; event: string; status: AnalysisStatus | "Complete" }[];
    files: { name: string; size: string; uploadedAt: string }[];
  };
  workbook: {
    sheets: { name: string; rows: number; cols: number }[];
    preview: { cell: string; value: string; formula?: string }[];
  };
  verification: {
    item: string;
    status: VerificationStatus;
    detail: string;
    checkedAt?: string;
  }[];
  decisionLog: {
    id: string;
    timestamp: string;
    type: DecisionType;
    title: string;
    reasoning: string;
    confidence: number;
  }[];
  summary: {
    rating: string;
    targetPrice: string;
    upside: string;
    sections: { heading: string; content: string }[];
    risks: string[];
    catalysts: string[];
  };
  chat: {
    role: "assistant" | "user";
    content: string;
    timestamp: string;
  }[];
}
