"use client";

import { useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import LessonsView from "./LessonsView";

export default function LessonsPageClient() {
  const router = useRouter();
  return (
    <div className="flex h-screen flex-col lg:flex-row">
      <div className="shrink-0 lg:h-full">
        <Sidebar onNewAnalysis={() => router.push("/?new=1")} />
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <LessonsView />
      </div>
    </div>
  );
}
