import { Suspense } from "react";
import HistoryPageClient from "@/components/HistoryPageClient";

export default function HistoryPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-background text-hap-muted">
          Loading history…
        </div>
      }
    >
      <HistoryPageClient />
    </Suspense>
  );
}
