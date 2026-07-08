"use client";

import { use, useEffect } from "react";
import { notFound } from "next/navigation";
import { useAnalysisStore } from "@/lib/analysis-store";
import AnalysisDetail from "@/components/analysis/AnalysisDetail";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default function AnalysisPage({ params }: PageProps) {
  const { id } = use(params);
  const { getById, refreshAnalysis, isLoading } = useAnalysisStore();
  const analysis = getById(id);

  useEffect(() => {
    void refreshAnalysis(id);
  }, [id, refreshAnalysis]);

  if (!analysis && isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-hap-muted">
        Loading analysis from backend...
      </div>
    );
  }

  if (!analysis) {
    notFound();
  }

  return <AnalysisDetail analysis={analysis} />;
}
