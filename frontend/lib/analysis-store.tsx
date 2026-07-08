"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnalysisStoreContext } from "./analysis-store-context";
import {
  createBackendAnalysis,
  checkBackendHealth,
  getBackendAnalysis,
  startBackendPipeline,
  uploadBackendAnalysisFiles,
} from "./api";
import {
  createLocalAnalysis,
  mapBackendAnalysis,
  syncAnalysisFromBackend,
} from "./analysis-pipeline";
import {
  readPersistedAnalyses,
  repairAnalyses,
  writePersistedAnalyses,
} from "./analysis-progress";
import { MOCK_ANALYSES } from "./mock-analyses";
import type { AnalysisDetail, NewAnalysisFormData } from "./types";

const PIPELINE_POLL_INTERVAL_MS = 10000;

export function AnalysisStoreProvider({ children }: { children: ReactNode }) {
  const [analyses, setAnalyses] = useState<AnalysisDetail[]>(() =>
    repairAnalyses(MOCK_ANALYSES),
  );
  const [hydrated, setHydrated] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(false);
  const analysesRef = useRef(analyses);

  useEffect(() => {
    analysesRef.current = analyses;
  }, [analyses]);

  useEffect(() => {
    setAnalyses(readPersistedAnalyses(MOCK_ANALYSES));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    writePersistedAnalyses(analyses);
  }, [analyses, hydrated]);

  useEffect(() => {
    if (!hydrated) return;

    let cancelled = false;

    const refreshBackendStatus = async () => {
      const available = await checkBackendHealth();
      if (!cancelled) setBackendAvailable(available);
    };

    refreshBackendStatus();
    const interval = setInterval(refreshBackendStatus, PIPELINE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [hydrated]);

  useEffect(() => {
    if (!hydrated || !backendAvailable) return;

    let cancelled = false;

    const pollBackendAnalyses = async () => {
      const backendLinked = analysesRef.current.filter(
        (analysis) => analysis.backendAnalysisId && !analysis.isDemo,
      );

      if (backendLinked.length === 0) return;

      const updates = await Promise.all(
        backendLinked.map(async (analysis) => {
          try {
            const backend = await getBackendAnalysis(analysis.backendAnalysisId!);
            return syncAnalysisFromBackend(analysis, backend);
          } catch {
            return analysis;
          }
        }),
      );

      if (cancelled) return;

      setAnalyses((prev) =>
        prev.map((analysis) => {
          const updated = updates.find((item) => item.id === analysis.id);
          return updated ?? analysis;
        }),
      );
    };

    pollBackendAnalyses();
    const interval = setInterval(pollBackendAnalyses, PIPELINE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [hydrated, backendAvailable]);

  const addAnalysis = useCallback(
    async (data: NewAnalysisFormData): Promise<string> => {
      if (!data.prefilledWorkbook || !data.customRunFilter) {
        throw new Error("Prefilled workbook and custom_run filter are required.");
      }

      const available = await checkBackendHealth();

      if (available) {
        const created = await createBackendAnalysis({
          company: data.companyName,
          ticker: data.ticker,
          analysisType:
            data.analysisType === "new_company"
              ? "New Company Initiation"
              : data.analysisType === "annual_update"
                ? "Annual Update"
                : "Quarterly Update",
        });

        const uploaded = await uploadBackendAnalysisFiles(created.analysis_id, {
          prefilledWorkbook: data.prefilledWorkbook,
          customRunFilter: data.customRunFilter,
          previousWorkbook: data.previousWorkbook,
        });

        await startBackendPipeline(uploaded.analysis_id);
        const refreshed = await getBackendAnalysis(uploaded.analysis_id);
        const mapped = mapBackendAnalysis(refreshed, data);

        setAnalyses((prev) => {
          const existing = prev.findIndex((a) => a.id === mapped.id);
          if (existing >= 0) {
            const updated = [...prev];
            updated[existing] = mapped;
            return updated;
          }
          return [mapped, ...prev.filter((item) => !item.isDemo)];
        });

        return mapped.id;
      }

      const local = {
        ...createLocalAnalysis(data),
        pipelineStage: "template_uploaded" as const,
        pipelineMessage:
          "Template and custom_run filter recorded locally. Start the HAP backend to run filing collection and workbook completion.",
        progress: 14,
        status: "Running" as const,
      };

      setAnalyses((prev) => {
        const existing = prev.findIndex((a) => a.id === local.id);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = local;
          return updated;
        }
        return [local, ...prev.filter((item) => !item.isDemo)];
      });

      return local.id;
    },
    [],
  );

  const getById = useCallback(
    (id: string) => analyses.find((a) => a.id === id.toLowerCase()),
    [analyses],
  );

  const value = useMemo(
    () => ({ analyses, addAnalysis, getById, backendAvailable }),
    [analyses, addAnalysis, getById, backendAvailable],
  );

  return (
    <AnalysisStoreContext.Provider value={value}>
      {children}
    </AnalysisStoreContext.Provider>
  );
}
