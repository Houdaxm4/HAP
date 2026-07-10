"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAnalysisStore } from "@/lib/analysis-store";
import Sidebar from "./Sidebar";
import CommandCenter from "./CommandCenter";
import AnalystChat from "./AnalystChat";
import NewAnalysisModal from "./NewAnalysisModal";

export default function Dashboard() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { refreshAnalyses } = useAnalysisStore();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setIsModalOpen(true);
    }
  }, [searchParams]);

  const openModal = () => setIsModalOpen(true);
  const closeModal = () => setIsModalOpen(false);

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
