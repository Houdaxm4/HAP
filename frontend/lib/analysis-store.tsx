"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AnalysisStoreContext } from "./analysis-store-context";
import { getAnalystLabel } from "./app_config";
import { MOCK_ANALYSES } from "./mock-analyses";
import type { AnalysisDetail, AnalysisStatus, NewAnalysisFormData } from "./types";

function typeLabel(type: NewAnalysisFormData["analysisType"]): string {
  const labels = {
    new_company: "New Company Initiation",
    annual_update: "Annual Update",
    quarterly_update: "Quarterly Update",
  };
  return labels[type];
}

const QUEUED_MAX_PROGRESS = 20;
const RUNNING_MAX_PROGRESS = 95;
const COMPLETE_PROGRESS = 100;

function advanceStatus(status: AnalysisStatus, progress: number): AnalysisStatus {
  if (status === "Queued" && progress >= QUEUED_MAX_PROGRESS) return "Running";
  if (status === "Running" && progress >= RUNNING_MAX_PROGRESS) return "Review";
  if (status === "Review" && progress >= COMPLETE_PROGRESS) return "Complete";
  return status;
}

function advanceProgress(status: AnalysisStatus, progress: number): number {
  if (status === "Complete") return COMPLETE_PROGRESS;
  if (status === "Review") return Math.min(COMPLETE_PROGRESS, progress + 1);
  if (status === "Queued") return Math.min(QUEUED_MAX_PROGRESS, progress + 2);
  return Math.min(
    RUNNING_MAX_PROGRESS,
    progress + Math.floor(Math.random() * 3) + 1,
  );
}

export function AnalysisStoreProvider({ children }: { children: ReactNode }) {
  const [analyses, setAnalyses] = useState<AnalysisDetail[]>(MOCK_ANALYSES);

  useEffect(() => {
    const interval = setInterval(() => {
      setAnalyses((prev) =>
        prev.map((analysis) => {
          if (analysis.status === "Complete") return analysis;

          const nextProgress = advanceProgress(analysis.status, analysis.progress);
          const nextStatus = advanceStatus(analysis.status, nextProgress);

          return {
            ...analysis,
            progress: nextProgress,
            status: nextStatus,
          };
        }),
      );
    }, 4000);

    return () => clearInterval(interval);
  }, []);

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
