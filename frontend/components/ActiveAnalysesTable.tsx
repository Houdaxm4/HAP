"use client";

import Link from "next/link";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import StatusBadge from "./StatusBadge";

export default function ActiveAnalysesTable() {
  const { analyses } = useAnalysisStore();

  return (
    <div className="overflow-hidden rounded border border-hap-border bg-hap-panel">
      <div className="border-b border-hap-border px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Active Analyses
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
              <th className="px-4 py-3 font-medium">Company</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Progress</th>
            </tr>
          </thead>
          <tbody>
            {analyses.map((row) => (
              <tr
                key={row.id}
                className="border-b border-hap-border/50 transition-colors hover:bg-hap-panel-elevated/50"
              >
                <td className="px-4 py-3">
                  <Link href={`/analysis/${row.id}`} className="group block">
                    <div className="font-medium group-hover:text-hap-orange">
                      {row.company}
                    </div>
                    <div className="font-mono text-xs text-hap-orange">{row.ticker}</div>
                  </Link>
                </td>
                <td className="px-4 py-3 text-hap-muted">{row.type}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={row.status} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-hap-border">
                      <div
                        className="h-full rounded-full bg-hap-orange transition-all duration-500"
                        style={{ width: `${row.progress}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs text-hap-muted">
                      {row.progress}%
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
