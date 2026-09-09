"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import type { NewAnalysisFormData } from "@/lib/types";
import Sidebar from "./Sidebar";
import HistoryView from "./HistoryView";
import NewAnalysisModal from "./NewAnalysisModal";

export default function HistoryPageClient() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { startAnalysis } = useAnalysisStore();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setIsModalOpen(true);
    }
  }, [searchParams]);

  const handleStartAnalysis = async (data: NewAnalysisFormData) => {
    const id = await startAnalysis(data);
    setIsModalOpen(false);
    router.push(`/analysis/${id}`);
  };

  return (
    <>
      <div className="flex h-screen flex-col lg:flex-row">
        <div className="shrink-0 lg:h-full">
          <Sidebar onNewAnalysis={() => setIsModalOpen(true)} />
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <HistoryView />
        </div>
      </div>
      <NewAnalysisModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleStartAnalysis}
      />
    </>
  );
}
