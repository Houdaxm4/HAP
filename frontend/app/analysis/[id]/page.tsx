"use client";

import { use, useEffect, useState } from "react";
import { notFound } from "next/navigation";
import { useAnalysisStore } from "@/lib/analysis-store";
import { getAnalysis } from "@/lib/api";
import AnalysisDetail from "@/components/analysis/AnalysisDetail";
import type { AnalysisRecord } from "@/lib/types";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default function AnalysisPage({ params }: PageProps) {
  const { id } = use(params);
  const { getById, upsertAnalysis, isLoading } = useAnalysisStore();
  const cached = getById(id);
  const [analysis, setAnalysis] = useState<AnalysisRecord | undefined>(cached);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (cached) {
      setAnalysis(cached);
      return;
    }
    let cancelled = false;
    void getAnalysis(id)
      .then((record) => {
        if (cancelled) return;
        upsertAnalysis(record);
        setAnalysis(record);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [cached, id, upsertAnalysis]);

  useEffect(() => {
    if (cached) setAnalysis(cached);
  }, [cached]);

  if (loadError) {
    notFound();
  }

  if (!analysis) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-hap-muted">
        {isLoading ? "Loading analysis..." : "Loading analysis from backend..."}
      </div>
    );
  }

  return <AnalysisDetail analysis={analysis} />;
}
