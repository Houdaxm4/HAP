"use client";

import { AnalysisStoreProvider } from "@/lib/analysis-store";

export function Providers({ children }: { children: React.ReactNode }) {
  return <AnalysisStoreProvider>{children}</AnalysisStoreProvider>;
}
