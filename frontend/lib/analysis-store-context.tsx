"use client";

import { createContext, useContext } from "react";
import type { AnalysisDetail, NewAnalysisFormData } from "./types";

export type AnalysisStoreContextValue = {
  analyses: AnalysisDetail[];
  isLoadingList: boolean;
  listError: string | null;
  reloadAnalyses: () => Promise<void>;
  startAnalysis: (data: NewAnalysisFormData) => Promise<string>;
  getById: (id: string) => AnalysisDetail | undefined;
  hydrateAnalysis: (analysisId: string) => Promise<AnalysisDetail | undefined>;
};

export const AnalysisStoreContext =
  createContext<AnalysisStoreContextValue | null>(null);

export function useAnalysisStore() {
  const ctx = useContext(AnalysisStoreContext);
  if (!ctx) {
    throw new Error("useAnalysisStore must be used within AnalysisStoreProvider");
  }
  return ctx;
}
