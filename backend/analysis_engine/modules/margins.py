"""Gross / operating / net / FCF margin analysis (scaffold).

Follow ``profitability.py`` for the full implementation pattern.
"""

from __future__ import annotations

from analysis_engine.base import AnalysisModule
from analysis_engine.schemas import AnalysisModuleResult
from canonical_model import CompanyFinancialModel


class MarginsModule(AnalysisModule):
    module_id = "margins"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        return AnalysisModuleResult(
            module_name=self.module_id,
            module_version=self.module_version,
            status="skipped",
            confidence=0.0,
            score=None,
            coverage={"implemented": False, "input_periods": model.periods},
            error="margins module is scaffolded but not implemented yet.",
        )
