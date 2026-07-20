"use client";

import { use, useEffect, useState } from "react";
import { notFound } from "next/navigation";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import AnalysisDetail from "@/components/analysis/AnalysisDetail";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default function AnalysisPage({ params }: PageProps) {
  const { id } = use(params);
  const { getById, hydrateAnalysis } = useAnalysisStore();
  const [isHydrating, setIsHydrating] = useState(() => !getById(id));
  const analysis = getById(id);

  useEffect(() => {
    if (getById(id)) {
      setIsHydrating(false);
      return;
    }

    let cancelled = false;

    void hydrateAnalysis(id).finally(() => {
      if (!cancelled) {
        setIsHydrating(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [getById, hydrateAnalysis, id]);

  if (!analysis && isHydrating) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-hap-muted">
        Loading analysis…
      </div>
    );
  }

  if (!analysis) {
    notFound();
  }

  return <AnalysisDetail analysis={analysis} />;
}
