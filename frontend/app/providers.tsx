"use client";

import { AnalysisStoreProvider } from "@/lib/analysis-store";
import { AuthProvider, useAuth } from "@/lib/auth";
import LoginScreen from "@/components/LoginScreen";

function Gate({ children }: { children: React.ReactNode }) {
  const { ready, authenticated } = useAuth();

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-hap-muted">
        Loading…
      </div>
    );
  }

  if (!authenticated) {
    return <LoginScreen />;
  }

  return <AnalysisStoreProvider>{children}</AnalysisStoreProvider>;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Gate>{children}</Gate>
    </AuthProvider>
  );
}
