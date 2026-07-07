"use client";

import { use } from "react";
import { notFound } from "next/navigation";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import AnalysisDetail from "@/components/analysis/AnalysisDetail";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default function AnalysisPage({ params }: PageProps) {
  const { id } = use(params);
  const { getById } = useAnalysisStore();
  const analysis = getById(id);

  if (!analysis) {
    notFound();
  }

  return <AnalysisDetail analysis={analysis} />;
}
