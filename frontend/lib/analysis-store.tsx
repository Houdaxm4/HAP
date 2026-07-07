"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createAnalysis } from "./api";
import { getAnalystGreeting, getAnalystLabel } from "./app_config";
import { MOCK_ANALYSES } from "./mock-analyses";
import type {
  AnalysisDetail,
  AnalysisStatus,
  ChatMessage,
  NewAnalysisFormData,
} from "./types";

type AnalysisStoreContextValue = {
  analyses: AnalysisDetail[];
  analystMessages: ChatMessage[];
  addAnalysis: (data: NewAnalysisFormData) => Promise<string>;
  getById: (id: string) => AnalysisDetail | undefined;
};

const AnalysisStoreContext = createContext<AnalysisStoreContextValue | null>(null);

function typeLabel(type: NewAnalysisFormData["analysisType"]): string {
  const labels = {
    new_company: "New Company",
    annual_update: "Annual Update",
    quarterly_update: "Quarterly Update",
  };
  return labels[type];
}

function formatTimestamp(): string {
  return new Date().toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function advanceStatus(status: AnalysisStatus, progress: number): AnalysisStatus {
  if (status === "Queued" && progress >= 20) return "Running";
  if (status === "Running" && progress >= 95) return "Review";
  if (status === "Review" && progress >= 100) return "Complete";
  return status;
}

function advanceProgress(status: AnalysisStatus, progress: number): number {
  if (status === "Complete") return 100;
  if (status === "Review") return Math.min(100, progress + 1);
  if (status === "Queued") return Math.min(20, progress + 2);
  return Math.min(94, progress + Math.floor(Math.random() * 3) + 1);
}

function isSimulatedStatus(status: AnalysisStatus): boolean {
  return status === "Queued" || status === "Running" || status === "Review";
}

const INITIAL_ANALYST_MESSAGE: ChatMessage = {
  id: "initial",
  role: "assistant",
  content: getAnalystGreeting(),
  timestamp: formatTimestamp(),
};

export function AnalysisStoreProvider({ children }: { children: ReactNode }) {
  const [analyses, setAnalyses] = useState<AnalysisDetail[]>(MOCK_ANALYSES);
  const [analystMessages, setAnalystMessages] = useState<ChatMessage[]>([
    INITIAL_ANALYST_MESSAGE,
  ]);

  useEffect(() => {
    const interval = setInterval(() => {
      setAnalyses((prev) =>
        prev.map((analysis) => {
          if (analysis.status === "Complete" || !isSimulatedStatus(analysis.status)) {
            return analysis;
          }

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

  const appendAnalystMessage = useCallback((content: string) => {
    setAnalystMessages((prev) => [
      ...prev,
      {
        id: `a-${Date.now()}`,
        role: "assistant",
        content,
        timestamp: formatTimestamp(),
      },
    ]);
  }, []);

  const addAnalysis = useCallback(
    async (data: NewAnalysisFormData): Promise<string> => {
      const response = await createAnalysis({
        company: data.companyName.trim(),
        ticker: data.ticker.trim().toUpperCase(),
        analysis_type: typeLabel(data.analysisType),
      });

      const now = new Date().toISOString();
      const newAnalysis: AnalysisDetail = {
        id: response.analysis_id,
        company: data.companyName.trim(),
        ticker: data.ticker.trim().toUpperCase(),
        type: typeLabel(data.analysisType),
        status: response.status,
        progress: 0,
        startedAt: now,
        analyst: getAnalystLabel(),
        sector: "Pending classification",
        marketCap: "—",
        thesis: data.notes || "Analysis created. Awaiting workbook upload.",
        priceTarget: "—",
        rating: "Pending",
        keyMetrics: [],
        workbookSheets: [],
        verificationChecks: [],
        decisionLog: [
          {
            id: `d-${Date.now()}`,
            timestamp: formatTimestamp(),
            agent: "Orchestrator",
            action: "Analysis created",
            detail: `${typeLabel(data.analysisType)} for ${data.ticker.toUpperCase()}`,
          },
        ],
        executiveSummary: "Analysis created. Upload workbooks to begin processing.",
        chatHistory: [
          {
            id: `c-${Date.now()}`,
            role: "assistant",
            content: "Analysis created successfully. Ready for file upload.",
            timestamp: formatTimestamp(),
          },
        ],
      };

      setAnalyses((prev) => [newAnalysis, ...prev]);
      appendAnalystMessage("Analysis created successfully. Ready for file upload.");

      return response.analysis_id;
    },
    [appendAnalystMessage],
  );

  const getById = useCallback(
    (id: string) => analyses.find((analysis) => analysis.id === id),
    [analyses],
  );

  const value = useMemo(
    () => ({ analyses, analystMessages, addAnalysis, getById }),
    [analyses, analystMessages, addAnalysis, getById],
  );

  return (
    <AnalysisStoreContext.Provider value={value}>
      {children}
    </AnalysisStoreContext.Provider>
  );
}

export function useAnalysisStore() {
  const ctx = useContext(AnalysisStoreContext);
  if (!ctx) {
    throw new Error("useAnalysisStore must be used within AnalysisStoreProvider");
  }
  return ctx;
}
