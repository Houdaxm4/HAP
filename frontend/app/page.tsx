import { Suspense } from "react";
import Dashboard from "@/components/Dashboard";

export default function Home() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-background text-hap-muted">
          Loading…
        </div>
      }
    >
      <Dashboard />
    </Suspense>
  );
}
