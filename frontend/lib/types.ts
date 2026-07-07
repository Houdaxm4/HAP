export type AnalysisStatus = "Running" | "Queued" | "Review" | "Complete";

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
