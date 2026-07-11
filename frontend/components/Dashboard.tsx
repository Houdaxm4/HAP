"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useAnalysisStore } from "@/lib/analysis-store";
import Sidebar from "./Sidebar";
import CommandCenter from "./CommandCenter";
import AnalystChat from "./AnalystChat";
import NewAnalysisModal from "./NewAnalysisModal";

export default function Dashboard() {
  const [manualOpen, setManualOpen] = useState(false);
  const { refreshAnalyses } = useAnalysisStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryOpen = searchParams.get("new") === "1";
  const isModalOpen = manualOpen || queryOpen;

  const openModal = () => setManualOpen(true);
  const closeModal = () => {
    setManualOpen(false);
    if (queryOpen) {
      router.replace("/");
    }
  };

  const handleStartAnalysis = async (analysisId: string) => {
    await refreshAnalyses();
    closeModal();
    router.push(`/analysis/${analysisId}`);
  };

  return (
    <>
      <div className="flex h-screen flex-col lg:flex-row">
        <div className="shrink-0 lg:h-full">
          <Sidebar onNewAnalysis={openModal} />
        </div>

        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <CommandCenter onNewAnalysis={openModal} />
          <AnalystChat />
        </div>
      </div>

      <NewAnalysisModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleStartAnalysis}
      />
    </>
  );
}
