"use client";

import { useEffect, useState } from "react";
import { getRecommendationConflict, type RecommendationConflict } from "@/lib/api";

export default function RecommendationConflictBanner({ analysisId }: { analysisId: string }) {
  const [info, setInfo] = useState<RecommendationConflict | null>(null);

  useEffect(() => {
    let active = true;
    getRecommendationConflict(analysisId)
      .then((value) => active && setInfo(value))
      .catch(() => active && setInfo(null));
    return () => {
      active = false;
    };
  }, [analysisId]);

  if (!info?.conflict) return null;
  return (
    <div role="alert" className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <strong>Recommendations disagree.</strong> {info.message}
    </div>
  );
}
