"use client";

import { use, useEffect, useState } from "react";
import { notFound } from "next/navigation";
import { useAnalysisStore } from "@/lib/analysis-store";
import { getAnalysis } from "@/lib/api";
import AnalysisDetail from "@/components/analysis/AnalysisDetail";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default function AnalysisPage({ params }: PageProps) {
  const { id } = use(params);
  const { getById, upsertAnalysis, isLoading } = useAnalysisStore();
  const analysis = getById(id);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (analysis) return;

    let cancelled = false;
    void getAnalysis(id)
      .then((record) => {
        if (!cancelled) upsertAnalysis(record);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      });

    return () => {
      cancelled = true;
    };
  }, [analysis, id, upsertAnalysis]);

  if (missing) {
    notFound();
  }

  if (!analysis) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-hap-muted">
        {isLoading ? "Loading analyses..." : "Loading analysis from backend..."}
      </div>
    );
  }

  return <AnalysisDetail analysis={analysis} />;
}
