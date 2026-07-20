"use client";

import ActiveAnalysesTable from "./ActiveAnalysesTable";

type CommandCenterProps = {
  onNewAnalysis: () => void;
};

function formatToday(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function CommandCenter({ onNewAnalysis }: CommandCenterProps) {
  return (
    <main className="flex h-full flex-1 flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-hap-border px-6 py-4 lg:px-8">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight lg:text-3xl">
            Command Center
          </h2>
          <p className="mt-0.5 text-xs text-hap-muted">{formatToday()}</p>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-8">
        <button
          onClick={onNewAnalysis}
          className="mb-8 flex w-full items-center justify-center gap-2 rounded border border-hap-orange/40 bg-hap-orange/10 px-6 py-4 text-base font-semibold text-hap-orange transition-all hover:border-hap-orange hover:bg-hap-orange/20 active:scale-[0.99] sm:w-auto sm:min-w-[240px]"
        >
          <span className="text-xl leading-none">+</span>
          New Analysis
        </button>

        <ActiveAnalysesTable />
      </div>
    </main>
  );
}
