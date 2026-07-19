"""
Legacy mapping-table models — deprecated.

HAP v1 uses Bloomberg Custom_Run_Filter workbooks parsed into CustomRunData.
See ingestion/models/custom_run_data.py.
"""

from __future__ import annotations

from ingestion.models.custom_run_data import CustomRunData

# Backward-compatible alias for imports that expected a "mapping" object.
CustomRunMapping = CustomRunData

__all__ = ["CustomRunData", "CustomRunMapping"]
