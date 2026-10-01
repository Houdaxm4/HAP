"""Re-run the deterministic analysis from saved inputs (no network, no Excel, no AI)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORT_INPUTS = {
    "valuation": "valuation_validation_report.json",
    "roic": "roic_validation_report.json",
    "expected_return": "expected_return_validation_report.json",
    "statement_validation": "statement_validation_report.json",
    "analyst_review": "analyst_review_report.json",
}
MODEL_FILE = "company_financial_model.json"
INPUT_FILES = (MODEL_FILE, *REPORT_INPUTS.values())


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def replay(inputs_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return (engine_result, final_recommendation) recomputed from ``inputs_dir``."""
    from analysis_engine.runner import AnalysisEngine
    from canonical_model import CompanyFinancialModel
    from services.final_recommendation_service import FinalRecommendationService

    raw_model = _load(inputs_dir / MODEL_FILE)
    if raw_model is None:
        raise FileNotFoundError(f"{MODEL_FILE} missing in {inputs_dir}")
    model = CompanyFinancialModel.model_validate(raw_model)
    engine = json.loads(AnalysisEngine().run(model).model_dump_json())

    reports = {key: _load(inputs_dir / name) for key, name in REPORT_INPUTS.items()}
    final = None
    # Same condition the pipeline uses: a final recommendation exists only when a valuation or ROIC report exists.
    # Like the pipeline, the engine scores are NOT passed in (see docs: the two recommendation systems are separate).
    if reports["valuation"] is not None or reports["roic"] is not None:
        result = FinalRecommendationService().synthesize(
            analysis_id=str(raw_model.get("analysis_id", "regression")),
            ticker=str(raw_model.get("ticker", "")),
            **reports,
        )
        final = json.loads(result.model_dump_json())
    return engine, final
