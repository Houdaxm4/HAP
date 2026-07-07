"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AnalysisDetail as AnalysisDetailType } from "@/lib/types";
import Sidebar from "../Sidebar";
import AnalystChat from "../AnalystChat";
import AnalysisHeader from "./AnalysisHeader";
import AnalysisTabs, { type AnalysisTab } from "./AnalysisTabs";
import OverviewTab from "./tabs/OverviewTab";
import WorkbookTab from "./tabs/WorkbookTab";
import VerificationTab from "./tabs/VerificationTab";
import DecisionLogTab from "./tabs/DecisionLogTab";
import SummaryTab from "./tabs/SummaryTab";
import AnalysisChatTab from "./tabs/AnalysisChatTab";

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
      case "Workbook":
        return <WorkbookTab analysis={analysis} />;
      case "Verification":
        return <VerificationTab analysis={analysis} />;
      case "Decision Log":
        return <DecisionLogTab analysis={analysis} />;
      case "Summary":
        return <SummaryTab analysis={analysis} />;
      case "Chat":
        return <AnalysisChatTab analysis={analysis} />;
    }
  };

  return (
    <div className="flex h-screen flex-col lg:flex-row">
      <div className="shrink-0 lg:h-full">
        <Sidebar onNewAnalysis={() => router.push("/?new=1")} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <AnalysisHeader analysis={analysis} />
          <AnalysisTabs activeTab={activeTab} onTabChange={setActiveTab} />
          <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-8">
            {renderTab()}
          </div>
        </div>
        <AnalystChat />
      </div>
    </div>
  );
}
