"""Local JSON persistence for analysis records."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from models.analysis import Analysis, CreateAnalysisRequest

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "analyses"


class AnalysisNotFoundError(Exception):
    """Raised when an analysis record does not exist."""


class AnalysisService:
    """Create, read, and update analysis metadata stored as JSON files."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, analysis_id: str) -> Path:
        return self.storage_dir / f"{analysis_id}.json"

    def create(self, request: CreateAnalysisRequest) -> Analysis:
        """Create a new analysis and persist it to disk."""
        analysis = Analysis(
            analysis_id=str(uuid.uuid4()),
            company=request.company.strip(),
            ticker=request.ticker.strip().upper(),
            analysis_type=request.analysis_type.strip(),
            status="created",
        )
        self.save(analysis)
        return analysis

    def get(self, analysis_id: str) -> Analysis:
        """Load an analysis by ID."""
        path = self._path_for(analysis_id)
        if not path.exists():
            raise AnalysisNotFoundError(f"Analysis '{analysis_id}' not found.")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return Analysis.from_dict(data)

    def save(self, analysis: Analysis) -> Analysis:
        """Persist the analysis record to disk."""
        path = self._path_for(analysis.analysis_id)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(analysis.to_dict(), handle, indent=2)
        return analysis

    def update(self, analysis: Analysis) -> Analysis:
        """Update an existing analysis record."""
        if not self._path_for(analysis.analysis_id).exists():
            raise AnalysisNotFoundError(f"Analysis '{analysis.analysis_id}' not found.")
        return self.save(analysis)

    def list_all(self) -> list[Analysis]:
        """Return all persisted analyses, newest first."""
        analyses: list[Analysis] = []
        for path in self.storage_dir.glob("*.json"):
            with path.open("r", encoding="utf-8") as handle:
                analyses.append(Analysis.from_dict(json.load(handle)))
        analyses.sort(key=lambda item: item.updated_at, reverse=True)
        return analyses
