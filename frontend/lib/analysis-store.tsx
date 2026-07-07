"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AnalysisStoreContext } from "./analysis-store-context";
import {
  readPersistedAnalyses,
  repairAnalyses,
  tickAnalysis,
  writePersistedAnalyses,
} from "./analysis-progress";
import { getAnalystLabel } from "./app_config";
import { MOCK_ANALYSES } from "./mock-analyses";
import type { AnalysisDetail, NewAnalysisFormData } from "./types";

const TICK_INTERVAL_MS = 4000;

function typeLabel(type: NewAnalysisFormData["analysisType"]): string {
  const labels = {
    new_company: "New Company Initiation",
    annual_update: "Annual Update",
    quarterly_update: "Quarterly Update",
  };
  return labels[type];
}

export function AnalysisStoreProvider({ children }: { children: ReactNode }) {
  const [analyses, setAnalyses] = useState<AnalysisDetail[]>(() =>
    repairAnalyses(MOCK_ANALYSES),
  );
  const [hydrated, setHydrated] = useState(false);

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

    const interval = setInterval(() => {
      setAnalyses((prev) => prev.map(tickAnalysis));
    }, TICK_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [hydrated]);

  const addAnalysis = useCallback((data: NewAnalysisFormData): string => {
    const id = data.ticker.toLowerCase();
    const newAnalysis: AnalysisDetail = {
      id,
      company: data.companyName,
      ticker: data.ticker.toUpperCase(),
      type: typeLabel(data.analysisType),
      status: "Queued",
      progress: 5,
      startedAt: new Date().toISOString(),
      analyst: getAnalystLabel(),
      sector: "Pending classification",
      marketCap: "—",
      thesis: data.notes || "Analysis initiated. Awaiting data ingestion.",
      priceTarget: "—",
      rating: "Pending",
      keyMetrics: [],
      workbookSheets: [
        {
          name: "Model",
          rows: 0,
          lastUpdated: "Just now",
          status: "pending",
        },
      ],
      verificationChecks: [],
      decisionLog: [
        {
          id: `d-${Date.now()}`,
          timestamp: new Date().toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
          }),
          agent: "Orchestrator",
          action: "Run initiated",
          detail: `${typeLabel(data.analysisType)} for ${data.ticker.toUpperCase()}`,
        },
      ],
      executiveSummary: "Analysis queued. Workbooks uploaded and awaiting processing.",
      chatHistory: [
        {
          id: `c-${Date.now()}`,
          role: "assistant",
          content: `Starting ${typeLabel(data.analysisType)} for ${data.companyName} (${data.ticker.toUpperCase()}). I'll notify you when data ingestion completes.`,
          timestamp: new Date().toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
          }),
        },
      ],
    };

    setAnalyses((prev) => {
      const existing = prev.findIndex((a) => a.id === id);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = newAnalysis;
        return updated;
      }
      return [newAnalysis, ...prev];
    });

    return id;
  }, []);

  const getById = useCallback(
    (id: string) => analyses.find((a) => a.id === id.toLowerCase()),
    [analyses],
  );

  const value = useMemo(
    () => ({ analyses, addAnalysis, getById }),
    [analyses, addAnalysis, getById],
  );

  return (
    <AnalysisStoreContext.Provider value={value}>
      {children}
    </AnalysisStoreContext.Provider>
  );
}
