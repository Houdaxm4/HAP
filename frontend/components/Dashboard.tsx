"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import type { NewAnalysisFormData } from "@/lib/types";
import Sidebar from "./Sidebar";
import CommandCenter from "./CommandCenter";
import AnalystChat from "./AnalystChat";
import NewAnalysisModal from "./NewAnalysisModal";

export default function Dashboard() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { addAnalysis } = useAnalysisStore();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setIsModalOpen(true);
    }
  }, [searchParams]);

  const openModal = () => setIsModalOpen(true);
  const closeModal = () => setIsModalOpen(false);

  const handleStartAnalysis = (data: NewAnalysisFormData) => {
    const id = addAnalysis(data);
    closeModal();
    router.push(`/analysis/${id}`);
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
