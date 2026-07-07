"use client";

import { AnalysisStoreProvider } from "@/lib/analysis-store";

export default function HapLayout({ children }: { children: React.ReactNode }) {
  return <AnalysisStoreProvider>{children}</AnalysisStoreProvider>;
}
