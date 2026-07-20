"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  createAnalysis,
  getAnalysis,
  getAnalysisOutputJson,
  isAnalysisTerminal,
  listAnalyses,
  runAnalysis,
  uploadAnalysisFiles,
} from "./api";
import { AnalysisStoreContext } from "./analysis-store-context";
import {
  mapDetailDtoToAnalysisDetail,
  mapSummaryToAnalysisDetail,
} from "./map-backend-analysis";
import type {
  AnalysisDetail,
  AnalysisEngineResult,
  NewAnalysisFormData,
  ValidationReport,
} from "./types";

const POLL_INTERVAL_MS = 2500;

function upsertAnalysis(
  analyses: AnalysisDetail[],
  next: AnalysisDetail,
): AnalysisDetail[] {
  const index = analyses.findIndex((item) => item.id === next.id);
  if (index === -1) {
    return [next, ...analyses];
  }
  const updated = [...analyses];
  updated[index] = next;
  return updated;
}

async function loadDetailArtifacts(
  analysisId: string,
  hasEngineResult: boolean,
  hasValidationReport: boolean,
  previous?: AnalysisDetail,
): Promise<{
  engineResult: AnalysisEngineResult | null;
  validationReport: ValidationReport | null;
}> {
  let engineResult = previous?.engineResult ?? null;
  let validationReport = previous?.validationReport ?? null;

  if (hasEngineResult) {
    const fetched = await getAnalysisOutputJson<AnalysisEngineResult>(
      analysisId,
      "analysis_engine_result.json",
    );
    if (fetched) {
      engineResult = fetched;
    }
  }

  if (hasValidationReport) {
    const fetched = await getAnalysisOutputJson<ValidationReport>(
      analysisId,
      "validation_report.json",
    );
    if (fetched) {
      validationReport = fetched;
    }
  }

  return { engineResult, validationReport };
}

export function AnalysisStoreProvider({ children }: { children: ReactNode }) {
  const [analyses, setAnalyses] = useState<AnalysisDetail[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const pollingIdsRef = useRef<Set<string>>(new Set());
  const analysesRef = useRef<AnalysisDetail[]>([]);
  analysesRef.current = analyses;

  const startPolling = useCallback((analysisId: string) => {
    pollingIdsRef.current.add(analysisId);
  }, []);

  const stopPolling = useCallback((analysisId: string) => {
    pollingIdsRef.current.delete(analysisId);
  }, []);

  const applyDetail = useCallback(async (analysisId: string) => {
    const previous = analysesRef.current.find((item) => item.id === analysisId);
    const detail = await getAnalysis(analysisId);
    const mapped = mapDetailDtoToAnalysisDetail(detail, previous);

    if (detail.has_engine_result || detail.has_validation_report) {
      const artifacts = await loadDetailArtifacts(
        analysisId,
        detail.has_engine_result,
        detail.has_validation_report,
        previous,
      );
      mapped.engineResult = artifacts.engineResult;
      mapped.validationReport = artifacts.validationReport;
    }

    setAnalyses((prev) => upsertAnalysis(prev, mapped));

    if (isAnalysisTerminal(detail)) {
      stopPolling(analysisId);
    } else {
      startPolling(analysisId);
    }

    return mapped;
  }, [startPolling, stopPolling]);

  const loadAnalyses = useCallback(async () => {
    setIsLoadingList(true);
    setListError(null);
    try {
      const summaries = await listAnalyses();
      const details = summaries.map((summary) => {
        if (!summary.is_complete && summary.pipeline_state !== "failed") {
          startPolling(summary.analysis_id);
        }
        return mapSummaryToAnalysisDetail(summary);
      });
      setAnalyses(details);
    } catch (error) {
      setListError(error instanceof Error ? error.message : "Failed to load analyses.");
      setAnalyses([]);
    } finally {
      setIsLoadingList(false);
    }
  }, [startPolling]);

  useEffect(() => {
    void loadAnalyses();
  }, [loadAnalyses]);

  useEffect(() => {
    const poll = async () => {
      const ids = [...pollingIdsRef.current];
      if (ids.length === 0) {
        return;
      }
      await Promise.all(
        ids.map(async (analysisId) => {
          try {
            await applyDetail(analysisId);
          } catch {
            stopPolling(analysisId);
          }
        }),
      );
    };

    const interval = window.setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [applyDetail, stopPolling]);

  const startAnalysis = useCallback(
    async (data: NewAnalysisFormData): Promise<string> => {
      if (!data.prefilledWorkbook) {
        throw new Error("Prefilled workbook is required.");
      }

      const created = await createAnalysis({
        company: data.companyName,
        ticker: data.ticker,
        analysis_type: data.analysisType,
      });

      await uploadAnalysisFiles(created.analysis_id, {
        prefilledWorkbook: data.prefilledWorkbook,
        previousWorkbook: data.previousWorkbook,
        customRunFilter: data.customRunFilter,
      });

      await runAnalysis(created.analysis_id);
      await applyDetail(created.analysis_id);
      return created.analysis_id;
    },
    [applyDetail],
  );

  const hydrateAnalysis = useCallback(
    async (analysisId: string): Promise<AnalysisDetail | undefined> => {
      try {
        return await applyDetail(analysisId);
      } catch {
        return undefined;
      }
    },
    [applyDetail],
  );

  const getById = useCallback(
    (id: string) => analyses.find((analysis) => analysis.id === id),
    [analyses],
  );

  const value = useMemo(
    () => ({
      analyses,
      isLoadingList,
      listError,
      reloadAnalyses: loadAnalyses,
      startAnalysis,
      getById,
      hydrateAnalysis,
    }),
    [analyses, isLoadingList, listError, loadAnalyses, startAnalysis, getById, hydrateAnalysis],
  );

  return (
    <AnalysisStoreContext.Provider value={value}>
      {children}
    </AnalysisStoreContext.Provider>
  );
}
