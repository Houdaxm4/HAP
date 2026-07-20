"use client";

const TABS = [
  "Overview",
  "Business Quality",
  "Investment Attractiveness",
  "Valuation",
  "Expected Return",
  "Recommendation",
  "Verification",
  "Deliverables",
] as const;

export type AnalysisTab = (typeof TABS)[number];

type AnalysisTabsProps = {
  activeTab: AnalysisTab;
  onTabChange: (tab: AnalysisTab) => void;
};

export default function AnalysisTabs({ activeTab, onTabChange }: AnalysisTabsProps) {
  return (
    <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-hap-border px-6 lg:px-8">
      {TABS.map((tab) => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          className={`shrink-0 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === tab
              ? "border-hap-orange text-hap-orange"
              : "border-transparent text-hap-muted hover:text-foreground"
          }`}
        >
          {tab}
        </button>
      ))}
    </nav>
  );
}
