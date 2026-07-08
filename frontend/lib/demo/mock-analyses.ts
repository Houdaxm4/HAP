import type { Analysis, AnalysisDetail } from "../types";

export const mockAnalyses: Record<string, Analysis> = {
  aapl: {
    id: "aapl",
    company: "Apple Inc.",
    ticker: "AAPL",
    type: "DCF Valuation",
    status: "Running",
    progress: 72,
    startedAt: "2026-07-06T08:15:00Z",
    updatedAt: "2026-07-06T09:42:00Z",
    analyst: "HAP Analyst",
    sector: "Technology / Consumer Electronics",
    marketCap: "$3.12T",
    currentPrice: "$214.50",
    targetPrice: "$248.00",
    recommendation: "Buy",
    overview: {
      thesis:
        "Apple maintains durable ecosystem lock-in with Services growing 14% YoY. DCF implies 15% upside assuming stable iPhone ASP and margin expansion in Vision Pro cycle 2.",
      keyMetrics: [
        { label: "Revenue (TTM)", value: "$391.0B", change: "+2.1%" },
        { label: "Gross Margin", value: "46.2%", change: "+0.8pp" },
        { label: "FCF Yield", value: "3.4%", change: "-0.2pp" },
        { label: "P/E (NTM)", value: "28.4x", change: "+1.2x" },
        { label: "Services Rev", value: "$96.2B", change: "+14.0%" },
        { label: "Net Cash", value: "$48.7B" },
      ],
      timeline: [
        { time: "08:15", event: "Analysis initiated", status: "Complete" },
        { time: "08:22", event: "Workbook ingested", status: "Complete" },
        { time: "08:45", event: "Revenue model built", status: "Complete" },
        { time: "09:10", event: "DCF sensitivity run", status: "Running" },
        { time: "09:30", event: "Peer comp verification", status: "Queued" },
        { time: "—", event: "Final summary generation", status: "Queued" },
      ],
      files: [
        { name: "AAPL_Prefilled_v3.xlsx", size: "2.4 MB", uploadedAt: "08:15" },
        { name: "AAPL_Previous_Q1.xlsx", size: "2.1 MB", uploadedAt: "08:15" },
        { name: "custom_run_filter.csv", size: "12 KB", uploadedAt: "08:15" },
      ],
    },
    workbook: {
      sheets: [
        { name: "Summary", rows: 48, cols: 12 },
        { name: "Income Statement", rows: 120, cols: 18 },
        { name: "DCF Model", rows: 200, cols: 24 },
        { name: "Sensitivity", rows: 64, cols: 16 },
        { name: "Comps", rows: 36, cols: 14 },
      ],
      preview: [
        { cell: "B4", value: "Apple Inc." },
        { cell: "B5", value: "AAPL" },
        { cell: "E12", value: "$248.00", formula: "=DCF!H45" },
        { cell: "E13", value: "15.6%", formula: "=(E12-B5)/B5" },
        { cell: "H22", value: "8.5%", formula: "=WACC_calc" },
        { cell: "H23", value: "3.2%" },
        { cell: "H24", value: "2.8%" },
        { cell: "C30", value: "$96.2B", formula: "=SUM(Services!C5:C16)" },
      ],
    },
    verification: [
      {
        item: "Revenue growth vs. consensus",
        status: "pass",
        detail: "Within 1.2% of Street estimates",
        checkedAt: "09:05",
      },
      {
        item: "Margin assumptions",
        status: "pass",
        detail: "Gross margin 46.2% — within historical range",
        checkedAt: "09:08",
      },
      {
        item: "WACC calculation",
        status: "warning",
        detail: "Beta sourced from 2Y weekly — consider 5Y",
        checkedAt: "09:12",
      },
      {
        item: "Terminal growth rate",
        status: "pass",
        detail: "2.8% — below GDP + inflation guardrail",
        checkedAt: "09:14",
      },
      {
        item: "Share count dilution",
        status: "pass",
        detail: "Buyback assumptions match trailing 4Q avg",
        checkedAt: "09:18",
      },
      {
        item: "Peer multiple cross-check",
        status: "pending",
        detail: "Awaiting comp set refresh",
      },
      {
        item: "Balance sheet items",
        status: "pass",
        detail: "Cash & debt reconciled to 10-Q",
        checkedAt: "09:22",
      },
      {
        item: "FX exposure",
        status: "fail",
        detail: "EUR/USD assumption stale — last updated Q4'25",
        checkedAt: "09:25",
      },
    ],
    decisionLog: [
      {
        id: "d1",
        timestamp: "08:25",
        type: "data",
        title: "Used Q2 FY26 10-Q for revenue baseline",
        reasoning:
          "Most recent filing available. Pre-announcement estimates excluded per run filter.",
        confidence: 0.95,
      },
      {
        id: "d2",
        timestamp: "08:38",
        type: "assumption",
        title: "Services growth set to 12% CAGR (5Y)",
        reasoning:
          "Trailing 3Y CAGR is 14.2%. Conservative haircut applied for App Store regulatory risk.",
        confidence: 0.82,
      },
      {
        id: "d3",
        timestamp: "08:52",
        type: "model",
        title: "Switched DCF terminal method to Gordon Growth",
        reasoning:
          "FCF profile stabilizing post-COVID cycle. Exit multiple cross-check within 5%.",
        confidence: 0.88,
      },
      {
        id: "d4",
        timestamp: "09:15",
        type: "override",
        title: "iPhone units: used internal est. over consensus",
        reasoning:
          "Supply chain checks suggest Q3 beat. +2M units vs. Street.",
        confidence: 0.71,
      },
      {
        id: "d5",
        timestamp: "09:30",
        type: "data",
        title: "Beta recalculated: 1.18 → 1.22",
        reasoning: "2Y weekly regression with SPY. R² = 0.74.",
        confidence: 0.91,
      },
    ],
    summary: {
      rating: "Buy",
      targetPrice: "$248.00",
      upside: "+15.6%",
      sections: [
        {
          heading: "Investment Thesis",
          content:
            "Apple's ecosystem moat remains the strongest in consumer tech. Services attach rate continues climbing, now 95% of installed base. Vision Pro gen-2 could open a new revenue leg by FY28. We see 15% upside to current levels on a 12-month view.",
        },
        {
          heading: "Valuation",
          content:
            "Our DCF yields $248 target (8.5% WACC, 2.8% terminal growth). Implied NTM P/E of 31.2x is a premium to hardware peers but justified by Services mix shift and capital return program.",
        },
        {
          heading: "Key Risks",
          content:
            "China revenue exposure (~18%), App Store regulatory actions in EU/US, and iPhone replacement cycle elongation remain the primary downside vectors.",
        },
      ],
      risks: [
        "China geopolitical / demand risk",
        "App Store fee compression (EU DMA)",
        "iPhone super-cycle failure",
        "FX headwinds (EUR weakness)",
      ],
      catalysts: [
        "Q3 FY26 earnings (Jul 31)",
        "Vision Pro gen-2 announcement",
        "Services bundling expansion",
        "$110B buyback authorization utilization",
      ],
    },
    chat: [
      {
        role: "assistant",
        content:
          "I've started the AAPL DCF valuation. Revenue baseline pulled from Q2 FY26 10-Q. Anything specific you want me to stress-test?",
        timestamp: "08:16",
      },
      {
        role: "user",
        content:
          "Focus on Services growth assumptions. Use conservative regulatory haircut.",
        timestamp: "08:18",
      },
      {
        role: "assistant",
        content:
          "Understood. I've set Services CAGR to 12% (down from trailing 14.2%) to account for EU DMA and US antitrust risk. Sensitivity table updating now.",
        timestamp: "08:20",
      },
      {
        role: "assistant",
        content:
          "Heads up — FX assumption for EUR/USD is stale (Q4'25). Want me to refresh from latest forward curve?",
        timestamp: "09:26",
      },
    ],
  },

  nvda: {
    id: "nvda",
    company: "NVIDIA Corp.",
    ticker: "NVDA",
    type: "Competitive Moat",
    status: "Queued",
    progress: 15,
    startedAt: "2026-07-06T09:00:00Z",
    updatedAt: "2026-07-06T09:05:00Z",
    analyst: "HAP Analyst",
    sector: "Technology / Semiconductors",
    marketCap: "$3.45T",
    currentPrice: "$142.80",
    targetPrice: "—",
    recommendation: "—",
    overview: {
      thesis:
        "Queued — competitive moat analysis pending workbook ingestion.",
      keyMetrics: [
        { label: "Revenue (TTM)", value: "$130.5B" },
        { label: "Gross Margin", value: "75.0%" },
        { label: "Data Center %", value: "87%" },
      ],
      timeline: [
        { time: "09:00", event: "Analysis queued", status: "Complete" },
        { time: "—", event: "Workbook ingestion", status: "Queued" },
      ],
      files: [],
    },
    workbook: { sheets: [], preview: [] },
    verification: [],
    decisionLog: [],
    summary: {
      rating: "—",
      targetPrice: "—",
      upside: "—",
      sections: [],
      risks: [],
      catalysts: [],
    },
    chat: [
      {
        role: "assistant",
        content:
          "NVDA competitive moat analysis is queued. I'll begin once the workbook is processed.",
        timestamp: "09:01",
      },
    ],
  },

  msft: {
    id: "msft",
    company: "Microsoft Corp.",
    ticker: "MSFT",
    type: "Earnings Preview",
    status: "Review",
    progress: 95,
    startedAt: "2026-07-05T14:00:00Z",
    updatedAt: "2026-07-06T08:30:00Z",
    analyst: "HAP Analyst",
    sector: "Technology / Software",
    marketCap: "$3.28T",
    currentPrice: "$442.10",
    targetPrice: "$510.00",
    recommendation: "Buy",
    overview: {
      thesis:
        "Azure AI revenue inflection driving re-rating. Q4 FY26 preview suggests Azure growth re-acceleration to 34% CC.",
      keyMetrics: [
        { label: "Revenue (TTM)", value: "$262.0B", change: "+15.2%" },
        { label: "Azure Growth", value: "34% CC", change: "+3pp" },
        { label: "Op. Margin", value: "45.1%", change: "+1.4pp" },
      ],
      timeline: [
        { time: "14:00", event: "Analysis initiated", status: "Complete" },
        { time: "16:30", event: "Earnings model complete", status: "Complete" },
        { time: "08:00", event: "Summary generated", status: "Complete" },
        { time: "—", event: "Awaiting analyst review", status: "Review" },
      ],
      files: [
        { name: "MSFT_Earnings_Q4.xlsx", size: "1.8 MB", uploadedAt: "14:00" },
      ],
    },
    workbook: {
      sheets: [
        { name: "Earnings Model", rows: 80, cols: 14 },
        { name: "Azure Breakdown", rows: 48, cols: 10 },
      ],
      preview: [
        { cell: "C8", value: "$64.7B", formula: "=Azure!B20" },
        { cell: "C12", value: "34%" },
      ],
    },
    verification: [
      {
        item: "Azure growth vs. guidance",
        status: "pass",
        detail: "Within management range",
        checkedAt: "16:00",
      },
      {
        item: "Copilot revenue attribution",
        status: "warning",
        detail: "Limited disclosure — estimate used",
        checkedAt: "16:15",
      },
    ],
    decisionLog: [
      {
        id: "d1",
        timestamp: "15:00",
        type: "assumption",
        title: "Azure CC growth: 34%",
        reasoning: "Channel checks + MSFT commentary.",
        confidence: 0.85,
      },
    ],
    summary: {
      rating: "Buy",
      targetPrice: "$510.00",
      upside: "+15.4%",
      sections: [
        {
          heading: "Earnings Preview",
          content:
            "Q4 FY26 EPS est. $3.42 vs. Street $3.35. Azure re-acceleration is the key catalyst.",
        },
      ],
      risks: ["Azure deceleration", "AI capex ROI scrutiny"],
      catalysts: ["Q4 earnings (Jul 22)", "Copilot monetization update"],
    },
    chat: [
      {
        role: "assistant",
        content:
          "MSFT earnings preview is ready for your review. Key delta is Azure at 34% CC vs. Street 31%.",
        timestamp: "08:30",
      },
    ],
  },
};

export function getAnalysis(id: string): Analysis | undefined {
  return mockAnalyses[id.toLowerCase()];
}

export function getAllAnalyses(): Analysis[] {
  return Object.values(mockAnalyses);
}

function mapVerificationStatus(
  status: Analysis["verification"][number]["status"],
): AnalysisDetail["verificationChecks"][number]["status"] {
  if (status === "pass") return "pass";
  if (status === "warning" || status === "fail") return "warn";
  return "pending";
}

function toAnalysisDetail(analysis: Analysis): AnalysisDetail {
  return {
    id: analysis.id,
    company: analysis.company,
    ticker: analysis.ticker,
    type: analysis.type,
    status: analysis.status,
    progress: analysis.progress,
    startedAt: analysis.startedAt,
    analyst: analysis.analyst,
    sector: analysis.sector,
    marketCap: analysis.marketCap,
    thesis: analysis.overview.thesis,
    priceTarget: analysis.targetPrice,
    rating: analysis.recommendation,
    keyMetrics: analysis.overview.keyMetrics,
    workbookSheets: analysis.workbook.sheets.map((sheet) => ({
      name: sheet.name,
      rows: sheet.rows,
      lastUpdated: analysis.updatedAt.slice(0, 10),
      status: "synced",
    })),
    verificationChecks: analysis.verification.map((check, index) => ({
      id: `v-${analysis.id}-${index}`,
      label: check.item,
      status: mapVerificationStatus(check.status),
      detail: check.detail,
    })),
    decisionLog: analysis.decisionLog.map((entry) => ({
      id: entry.id,
      timestamp: entry.timestamp,
      agent: entry.type,
      action: entry.title,
      detail: entry.reasoning,
    })),
    executiveSummary: analysis.summary.sections[0]?.content ?? analysis.summary.rating,
    chatHistory: analysis.chat.map((message, index) => ({
      id: `c-${analysis.id}-${index}`,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp,
    })),
  };
}

export const MOCK_ANALYSES: AnalysisDetail[] = Object.values(mockAnalyses).map(
  toAnalysisDetail,
);
