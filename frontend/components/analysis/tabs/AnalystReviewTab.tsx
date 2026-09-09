"use client";

import { useEffect, useState } from "react";
import {
  getAnalystReview,
  overrideRdUsefulLife,
  reviewLeaseRate,
} from "@/lib/api";
import type { AnalysisDetail } from "@/lib/types";

type ReviewPayload = {
  lease_rate_review: {
    status?: string;
    proposed_rate?: number | null;
    approved_rate?: number | null;
    supporting_evidence?: string[];
    prior_or_comparable_rates?: number[];
    calculated_lease_asset?: number | null;
    calculated_lease_liability?: number | null;
    sensitivity?: { rate?: number; role?: string }[];
    summary?: string;
    blocking?: boolean;
    proposal?: { methodology?: string; confidence?: number };
  } | null;
  rd_useful_life_decision: {
    selected_useful_life?: number | null;
    original_agent_selection?: number | null;
    warning?: string;
    rationale?: string;
    confidence?: number;
    permitted_range?: [number, number];
    analyst_override?: number | null;
  } | null;
};

export default function AnalystReviewTab({ analysis }: { analysis: AnalysisDetail }) {
  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rate, setRate] = useState("");
  const [reason, setReason] = useState("");
  const [rdLife, setRdLife] = useState("");
  const [rdReason, setRdReason] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAnalystReview(analysis.id)
      .then((data) => {
        if (!cancelled) {
          setPayload(data as ReviewPayload);
          if (data.lease_rate_review && typeof data.lease_rate_review === "object") {
            const proposed = (data.lease_rate_review as { proposed_rate?: number }).proposed_rate;
            if (proposed != null) setRate(String(proposed));
          }
          if (data.rd_useful_life_decision && typeof data.rd_useful_life_decision === "object") {
            const life = (data.rd_useful_life_decision as { selected_useful_life?: number })
              .selected_useful_life;
            if (life != null) setRdLife(String(life));
          }
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [analysis.id]);

  async function onLease(action: "approve" | "correct" | "request_more_evidence") {
    setBusy(true);
    setError(null);
    try {
      await reviewLeaseRate(analysis.id, {
        action,
        rate: action === "correct" ? Number(rate) : undefined,
        reason: reason || undefined,
      });
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRdOverride() {
    setBusy(true);
    setError(null);
    try {
      await overrideRdUsefulLife(analysis.id, {
        useful_life: Number(rdLife),
        reason: rdReason || undefined,
      });
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const lease = payload?.lease_rate_review;
  const rd = payload?.rd_useful_life_decision;

  return (
    <div className="space-y-6">
      {error ? (
        <p className="rounded border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      <section className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-hap-orange">
          Long-term lease rate — required review
        </h3>
        {!lease ? (
          <p className="mt-3 text-sm text-hap-muted">No lease-rate review is pending for this analysis.</p>
        ) : (
          <div className="mt-3 space-y-3 text-sm">
            <p>{lease.summary}</p>
            <p>
              Proposed rate:{" "}
              <span className="font-mono">
                {lease.proposed_rate == null ? "—" : `${(lease.proposed_rate * 100).toFixed(2)}%`}
              </span>
              {lease.proposal?.methodology ? ` via ${lease.proposal.methodology}` : ""}
            </p>
            <p>
              Calculated lease asset {lease.calculated_lease_asset ?? "—"} / liability{" "}
              {lease.calculated_lease_liability ?? "—"}
            </p>
            {lease.supporting_evidence?.length ? (
              <ul className="list-disc pl-5 text-hap-muted">
                {lease.supporting_evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
            {lease.sensitivity?.length ? (
              <p className="text-hap-muted">
                Sensitivity:{" "}
                {lease.sensitivity
                  .map((s) => `${s.role}=${s.rate == null ? "—" : (s.rate * 100).toFixed(2)}%`)
                  .join(" · ")}
              </p>
            ) : null}
            <label className="block text-xs uppercase tracking-wider text-hap-muted">
              Corrected rate (fraction, e.g. 0.045)
              <input
                className="mt-1 w-full rounded border border-hap-border bg-transparent px-3 py-2 font-mono"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
              />
            </label>
            <label className="block text-xs uppercase tracking-wider text-hap-muted">
              Reason
              <input
                className="mt-1 w-full rounded border border-hap-border bg-transparent px-3 py-2"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy || lease.blocking === false}
                onClick={() => onLease("approve")}
                className="rounded border border-hap-orange/40 bg-hap-orange/10 px-3 py-2 text-xs font-semibold text-hap-orange"
              >
                Approve
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onLease("correct")}
                className="rounded border border-hap-border px-3 py-2 text-xs font-semibold"
              >
                Correct
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onLease("request_more_evidence")}
                className="rounded border border-hap-border px-3 py-2 text-xs font-semibold"
              >
                Request more evidence
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="rounded border border-amber-500/40 bg-amber-500/10 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-amber-300">
          R&D useful life — agent-selected assumption
        </h3>
        {!rd ? (
          <p className="mt-3 text-sm text-hap-muted">No R&D useful-life decision is available yet.</p>
        ) : (
          <div className="mt-3 space-y-3 text-sm">
            <p className="font-semibold text-amber-200">{rd.warning}</p>
            <p>
              Selected life: <span className="font-mono">{rd.selected_useful_life ?? "—"} years</span>
              {rd.original_agent_selection != null
                ? ` (original agent selection ${rd.original_agent_selection})`
                : ""}
              {rd.analyst_override != null ? ` · override ${rd.analyst_override}` : ""}
            </p>
            <p className="text-hap-muted">{rd.rationale}</p>
            <label className="block text-xs uppercase tracking-wider text-hap-muted">
              Override useful life (years)
              <input
                className="mt-1 w-full rounded border border-hap-border bg-transparent px-3 py-2 font-mono"
                value={rdLife}
                onChange={(e) => setRdLife(e.target.value)}
              />
            </label>
            <label className="block text-xs uppercase tracking-wider text-hap-muted">
              Reason
              <input
                className="mt-1 w-full rounded border border-hap-border bg-transparent px-3 py-2"
                value={rdReason}
                onChange={(e) => setRdReason(e.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busy || !rdLife}
              onClick={onRdOverride}
              className="rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs font-semibold text-amber-200"
            >
              Override and recalculate
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
