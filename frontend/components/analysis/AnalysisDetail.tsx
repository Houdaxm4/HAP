"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AnalysisDetail as AnalysisDetailType } from "@/lib/types";
import Sidebar from "../Sidebar";
import RunActivityPanel from "../RunActivityPanel";
import AnalysisHeader from "./AnalysisHeader";
import AnalysisTabs, { type AnalysisTab } from "./AnalysisTabs";
import OverviewTab from "./tabs/OverviewTab";
import {
  BusinessQualityTab,
  InvestmentAttractivenessTab,
} from "./tabs/AggregatorTabs";
import { ExpectedReturnTab, ValuationTab } from "./tabs/ModuleTabs";
import RecommendationTab from "./tabs/RecommendationTab";
import VerificationTab from "./tabs/VerificationTab";
import DeliverablesTab from "./tabs/DeliverablesTab";

type AnalysisDetailProps = {
  analysis: AnalysisDetailType;
};

export default function AnalysisDetail({ analysis }: AnalysisDetailProps) {
  const [activeTab, setActiveTab] = useState<AnalysisTab>("Overview");
  const router = useRouter();

  const renderTab = () => {
    switch (activeTab) {
      case "Overview":
        return <OverviewTab analysis={analysis} />;
      case "Business Quality":
        return <BusinessQualityTab analysis={analysis} />;
      case "Investment Attractiveness":
        return <InvestmentAttractivenessTab analysis={analysis} />;
      case "Valuation":
        return <ValuationTab analysis={analysis} />;
      case "Expected Return":
        return <ExpectedReturnTab analysis={analysis} />;
      case "Recommendation":
        return <RecommendationTab analysis={analysis} />;
      case "Verification":
        return <VerificationTab analysis={analysis} />;
      case "Deliverables":
        return <DeliverablesTab analysis={analysis} />;
    }
  };

  return (
    <div className="flex h-screen flex-col lg:flex-row">
      <div className="shrink-0 lg:h-full">
        <Sidebar onNewAnalysis={() => router.push("/?new=1")} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <AnalysisHeader
            analysis={analysis}
            onOpenDeliverables={() => setActiveTab("Deliverables")}
          />
          <AnalysisTabs activeTab={activeTab} onTabChange={setActiveTab} />
          <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-8">
            {renderTab()}
          </div>
        </div>
        <RunActivityPanel analysis={analysis} />
      </div>
    </div>
  );
}
