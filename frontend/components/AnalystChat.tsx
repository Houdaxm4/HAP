"use client";

import { getAnalystLabel } from "@/lib/app_config";

export default function AnalystChat() {
  return (
    <aside className="flex h-full w-full flex-col border-t border-hap-border bg-hap-panel lg:w-80 lg:border-t-0 lg:border-l xl:w-96">
      <div className="flex shrink-0 items-center gap-3 border-b border-hap-border px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-hap-orange to-hap-orange-dim text-xs font-bold text-black">
          AI
        </div>
        <div>
          <h3 className="text-sm font-semibold">{getAnalystLabel()}</h3>
          <p className="text-[10px] text-hap-muted">Investment intelligence</p>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center px-5 py-4">
        <p className="text-center text-sm text-hap-muted">
          Analyst chat is not connected to the backend in this release.
        </p>
      </div>
    </aside>
  );
}
