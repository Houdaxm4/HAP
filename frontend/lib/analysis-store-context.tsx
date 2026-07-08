"use client";

import { createContext } from "react";
import type { AnalysisRecord } from "./types";

export type AnalysisStoreContextValue = {
  analyses: AnalysisRecord[];
  isLoading: boolean;
  error: string | null;
  refreshAnalyses: () => Promise<void>;
  refreshAnalysis: (analysisId: string) => Promise<void>;
  getById: (id: string) => AnalysisRecord | undefined;
  upsertAnalysis: (analysis: AnalysisRecord) => void;
};

export const AnalysisStoreContext = createContext<AnalysisStoreContextValue | null>(null);

export const POLL_INTERVAL_MS = 3000;
