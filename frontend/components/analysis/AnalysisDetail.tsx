"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { AnalysisRecord } from "@/lib/types";
import { useAnalysisStore } from "@/lib/analysis-store";
import { isActivePipelineStatus } from "@/lib/pipeline-stages";
import Sidebar from "../Sidebar";
import AnalystChat from "../AnalystChat";
import AnalysisHeader from "./AnalysisHeader";
import AnalysisTabs, { type AnalysisTab } from "./AnalysisTabs";
import PipelineStages from "./PipelineStages";
import OverviewTab from "./tabs/OverviewTab";
import WorkbookTab from "./tabs/WorkbookTab";
import VerificationTab from "./tabs/VerificationTab";
import DecisionLogTab from "./tabs/DecisionLogTab";
import SummaryTab from "./tabs/SummaryTab";
import AnalysisChatTab from "./tabs/AnalysisChatTab";

type AnalysisDetailProps = {
  analysis: AnalysisRecord;
};

export default function AnalysisDetail({ analysis }: AnalysisDetailProps) {
  const [activeTab, setActiveTab] = useState<AnalysisTab>("Overview");
  const router = useRouter();
  const { refreshAnalysis } = useAnalysisStore();

  useEffect(() => {
    if (!isActivePipelineStatus(analysis.displayStatus)) return;
    const interval = setInterval(() => {
      void refreshAnalysis(analysis.id);
    }, 2500);
    return () => clearInterval(interval);
  }, [analysis.displayStatus, analysis.id, refreshAnalysis]);

  const renderTab = () => {
    switch (activeTab) {
      case "Overview":
        return (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <OverviewTab analysis={analysis} />
            <PipelineStages analysis={analysis} />
          </div>
        );
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
