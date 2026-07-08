"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getAnalysis, listAnalyses } from "./api";
import {
  AnalysisStoreContext,
  POLL_INTERVAL_MS,
  type AnalysisStoreContextValue,
} from "./analysis-store-context";
import { isProcessingStatus } from "./pipeline-stages";
import type { AnalysisRecord } from "./types";

export function useAnalysisStore() {
  const ctx = useContext(AnalysisStoreContext);
  if (!ctx) {
    throw new Error("useAnalysisStore must be used within AnalysisStoreProvider");
  }
  return ctx;
}

export function AnalysisStoreProvider({ children }: { children: ReactNode }) {
  const [analyses, setAnalyses] = useState<AnalysisRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const analysesRef = useRef<AnalysisRecord[]>([]);

  useEffect(() => {
    analysesRef.current = analyses;
  }, [analyses]);

  const upsertAnalysis = useCallback((analysis: AnalysisRecord) => {
    setAnalyses((prev) => {
      const index = prev.findIndex((item) => item.id === analysis.id);
      if (index === -1) {
        return [analysis, ...prev];
      }
      const next = [...prev];
      next[index] = analysis;
      return next;
    });
  }, []);

  const refreshAnalyses = useCallback(async () => {
    try {
      const records = await listAnalyses();
      setAnalyses(records);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load analyses.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refreshAnalysis = useCallback(
    async (analysisId: string) => {
      try {
        const record = await getAnalysis(analysisId);
        upsertAnalysis(record);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to refresh analysis.");
      }
    },
    [upsertAnalysis],
  );

  const getById = useCallback(
    (id: string) => analyses.find((analysis) => analysis.id === id),
    [analyses],
  );

  useEffect(() => {
    void refreshAnalyses();
  }, [refreshAnalyses]);

  useEffect(() => {
    const interval = setInterval(() => {
      const active = analysesRef.current.filter((analysis) =>
        isProcessingStatus(analysis.displayStatus),
      );
      if (active.length === 0) {
        return;
      }
      void Promise.all(active.map((analysis) => refreshAnalysis(analysis.id)));
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [refreshAnalysis]);

  const value = useMemo<AnalysisStoreContextValue>(
    () => ({
      analyses,
      isLoading,
      error,
      refreshAnalyses,
      refreshAnalysis,
      getById,
      upsertAnalysis,
    }),
    [analyses, isLoading, error, refreshAnalyses, refreshAnalysis, getById, upsertAnalysis],
  );

  return (
    <AnalysisStoreContext.Provider value={value}>{children}</AnalysisStoreContext.Provider>
  );
}

// Re-export context for tests or advanced usage.
export { AnalysisStoreContext };
