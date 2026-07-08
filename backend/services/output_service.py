"""Output artifact storage for pipeline stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "storage" / "outputs"


class OutputService:
    """Read and write JSON artifacts under per-analysis output directories."""

    def __init__(self, outputs_dir: Path | None = None) -> None:
        self.outputs_dir = outputs_dir or OUTPUTS_DIR
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def analysis_output_dir(self, analysis_id: str) -> Path:
        """Return (and create) the output directory for an analysis."""
        directory = self.outputs_dir / analysis_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def write_json(self, analysis_id: str, filename: str, payload: dict[str, Any] | BaseModel) -> str:
        """Serialize a payload to JSON and return the relative artifact path."""
        directory = self.analysis_output_dir(analysis_id)
        path = directory / filename
        data = payload.model_dump() if isinstance(payload, BaseModel) else payload
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
        return f"outputs/{analysis_id}/{filename}"

    def read_json(self, analysis_id: str, filename: str) -> dict[str, Any]:
        """Load a JSON artifact from the analysis output directory."""
        path = self.analysis_output_dir(analysis_id) / filename
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def artifact_path(self, analysis_id: str, filename: str) -> Path:
        """Resolve an absolute path to an output artifact."""
        return self.analysis_output_dir(analysis_id) / filename

    def relative_path(self, analysis_id: str, filename: str) -> str:
        """Return the storage-relative path for an artifact."""
        return f"outputs/{analysis_id}/{filename}"
