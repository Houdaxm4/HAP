"use client";

import { useCallback, useEffect, useState } from "react";
import {
  answerCheckpoint,
  continueAgentRun,
  getAgentDossier,
  generateReportOpinion,
  getAgentRun,
  getReportOpinion,
  startAgentRun,
  type AgentDossier,
  type AgentRunState,
  type ReportOpinion,
} from "@/lib/api";

const PHASE_TEXT: Record<AgentRunState["phase"], string> = {
  not_started: "Not started",
  pipeline: "Running the analysis...",
  waiting_for_you: "Waiting for your feedback",
  revising: "You asked for changes",
  done: "Approved",
  stopped: "Stopped",
};

export default function AgentRunPanel({ analysisId }: { analysisId: string }) {
  const [state, setState] = useState<AgentRunState | null>(null);
  const [dossier, setDossier] = useState<AgentDossier | null>(null);
  const [withTake, setWithTake] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [opinion, setOpinion] = useState<ReportOpinion | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await getAgentRun(analysisId);
      setState(next);
      if (next.checkpoints.some((c) => c.kind === "final_review")) {
        setDossier(await getAgentDossier(analysisId).catch(() => null));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the run.");
    }
  }, [analysisId]);

  useEffect(() => {
    void refresh();
    getReportOpinion(analysisId).then(setOpinion).catch(() => setOpinion(null));
  }, [refresh, analysisId]);

  useEffect(() => {
    if (state?.phase !== "pipeline") return;
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [state?.phase, refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNote("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  const open = state?.checkpoints.find((c) => c.status === "open");
  const canStart = !state || ["not_started", "stopped", "revising", "done"].includes(state.phase);

  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-medium">{state ? PHASE_TEXT[state.phase] : "Loading..."}</span>
        {canStart && (
          <>
            <button
              className="rounded bg-black px-3 py-1.5 text-white disabled:opacity-50"
              disabled={busy}
              onClick={() => act(() => startAgentRun(analysisId, withTake))}
            >
              Run analysis with checkpoints
            </button>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={withTake} onChange={(e) => setWithTake(e.target.checked)} />
              Add &quot;my take&quot; (paid model, counts toward the monthly cap)
            </label>
          </>
        )}
        {state?.phase === "waiting_for_you" && open?.kind === "analyst_review" && (
          <button
            className="rounded border px-3 py-1.5"
            disabled={busy}
            onClick={() => act(() => continueAgentRun(analysisId, withTake))}
          >
            I resolved the review - continue
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}

      <div className="space-y-2 rounded border p-4">
        <h3 className="font-semibold">Analyst opinion in the Word report</h3>
        <p className="text-xs text-gray-600">
          Writes the fundamentals opinion (and the cheap/not-cheap view if fundamentals are strong) into the report from online
          sources and the workbook. Uses the paid model and counts toward the monthly cap. It is labeled as opinion and never
          changes HAP&apos;s scores.
        </p>
        <button
          className="rounded border px-3 py-1.5 disabled:opacity-50"
          disabled={busy}
          onClick={() => act(async () => setOpinion(await generateReportOpinion(analysisId)))}
        >
          {opinion ? "Regenerate opinion" : "Add opinion to the report"}
        </button>
        {opinion && (
          <div className="space-y-2 rounded bg-violet-50 p-3 text-violet-950">
            <div className="text-xs font-semibold uppercase">Opinion - {opinion.label}</div>
            <p className="whitespace-pre-wrap">{opinion.fundamentals}</p>
            {opinion.valuation && <p className="whitespace-pre-wrap">{opinion.valuation}</p>}
            <p className="text-xs text-gray-600">
              {opinion.model} - {opinion.outside_sources.length} outside source(s) - inserted into {opinion.inserted_into}
            </p>
          </div>
        )}
      </div>

      {dossier && (
        <div className="space-y-3 rounded border p-4">
          <h3 className="font-semibold">
            Dossier: {dossier.company} ({dossier.ticker})
          </h3>
          <p>
            <strong>Headline (rules-based, workbook):</strong> {dossier.headline.headline ?? "none"}
            {dossier.headline.conflict && (
              <span className="ml-2 text-amber-800">Engine says {dossier.headline.engine_recommendation}</span>
            )}
          </p>
          {dossier.flags.length > 0 && (
            <ul className="list-disc pl-5 text-amber-900">
              {dossier.flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
          {dossier.my_take?.text && (
            <div className="rounded bg-violet-50 p-3 text-violet-950">
              <div className="mb-1 text-xs font-semibold uppercase">My take - {dossier.my_take.label}</div>
              <p className="whitespace-pre-wrap">{dossier.my_take.text}</p>
            </div>
          )}
          {dossier.my_take?.error && <p className="text-xs text-gray-600">My take unavailable: {dossier.my_take.error}</p>}
          <details>
            <summary className="cursor-pointer font-medium">Outside evidence ({dossier.outside_evidence.items.length})</summary>
            <ul className="mt-2 space-y-2">
              {dossier.outside_evidence.items.map((item) => (
                <li key={item.url} className="rounded bg-gray-50 p-2">
                  <div className="font-medium">{item.title || item.kind}</div>
                  <div className="text-xs text-gray-600">
                    {item.source} - as of {item.as_of ?? "unknown"} - {item.reliability_note}
                  </div>
                  <pre className="mt-1 whitespace-pre-wrap text-xs">{item.content.slice(0, 600)}</pre>
                </li>
              ))}
            </ul>
            {dossier.outside_evidence.errors.map((e) => (
              <p key={e} className="text-xs text-gray-600">
                {e}
              </p>
            ))}
          </details>
          <p className="text-xs text-gray-600">{dossier.note}</p>
        </div>
      )}

      {open && (
        <div className="rounded border-2 border-black p-4">
          <h3 className="font-semibold">{open.title}</h3>
          <p className="mt-1">{open.summary}</p>
          <textarea
            className="mt-3 w-full rounded border p-2"
            rows={2}
            maxLength={2000}
            placeholder="Why? (optional, but this is how HAP learns)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            {open.options.map((option) => (
              <button
                key={option}
                className="rounded border px-3 py-1.5 capitalize disabled:opacity-50"
                disabled={busy}
                onClick={() => act(() => answerCheckpoint(analysisId, open.id, option as "approve" | "revise" | "stop", note))}
              >
                {option === "revise" ? "Needs changes" : option}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
