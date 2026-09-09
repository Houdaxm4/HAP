"""Validate already-present prefilled cells against SEC/CFM candidates."""

from __future__ import annotations

from typing import Any

from models.completion import CompletionDecision, CompletionReport
from models.prefill_validation import (
    PrefillValidationEntry,
    PrefillValidationReport,
    PrefillValidationStatus,
)


def values_agree(
    workbook_value: Any,
    sec_value: Any,
    *,
    tol_abs: float = 0.51,
    tol_rel: float = 0.001,
) -> bool:
    """Return True when workbook and SEC values agree within tolerance."""
    if workbook_value is None or sec_value is None:
        return False
    if isinstance(workbook_value, str) and isinstance(sec_value, str):
        return workbook_value.strip() == sec_value.strip()
    try:
        left = float(workbook_value)
        right = float(sec_value)
    except (TypeError, ValueError):
        return str(workbook_value).strip() == str(sec_value).strip()
    if abs(left - right) <= tol_abs:
        return True
    denom = abs(left) if abs(left) > 1e-12 else abs(right)
    if denom > 1e-12 and abs(left - right) / denom <= tol_rel:
        return True
    return False


class PrefillValidationService:
    """
    Phase B — after completion.

    Compares ALREADY_PRESENT cells to SEC/CFM proposed values.
    Never rewrites the workbook; discrepancies are recorded only.
    """

    def validate(self, completion: CompletionReport) -> PrefillValidationReport:
        entries: list[PrefillValidationEntry] = []
        for item in completion.entries:
            # In-scope ALREADY_PRESENT, plus OUT_OF_SCOPE populated cells
            # (historical review moves to validation, not completion).
            reviewable = item.decision == CompletionDecision.ALREADY_PRESENT or (
                item.decision == CompletionDecision.OUT_OF_SCOPE
                and item.workbook_value is not None
                and not (
                    isinstance(item.workbook_value, str) and item.workbook_value.strip() == ""
                )
            )
            if not reviewable:
                continue
            if item.proposed_value is None:
                entries.append(
                    PrefillValidationEntry(
                        intent_id=item.intent_id,
                        mapping_id=item.mapping_id,
                        sheet=item.sheet,
                        cell=item.cell,
                        cell_ref=item.cell_ref,
                        metric=item.metric,
                        period=item.period,
                        status=PrefillValidationStatus.SKIPPED,
                        workbook_value=item.workbook_value,
                        sec_value=None,
                        source_evidence=item.source,
                        reason="No SEC/CFM candidate available for comparison",
                    )
                )
                continue

            agree = values_agree(item.workbook_value, item.proposed_value)
            if agree:
                entries.append(
                    PrefillValidationEntry(
                        intent_id=item.intent_id,
                        mapping_id=item.mapping_id,
                        sheet=item.sheet,
                        cell=item.cell,
                        cell_ref=item.cell_ref,
                        metric=item.metric,
                        period=item.period,
                        status=PrefillValidationStatus.VALIDATED,
                        workbook_value=item.workbook_value,
                        sec_value=item.proposed_value,
                        difference=0.0,
                        difference_pct=0.0,
                        source_evidence=item.source,
                        reason="Workbook/Bloomberg value agrees with SEC within tolerance",
                        correction_applied=False,
                    )
                )
                continue

            try:
                left = float(item.workbook_value)
                right = float(item.proposed_value)
                diff = right - left
                pct = (diff / left) if abs(left) > 1e-12 else None
            except (TypeError, ValueError):
                diff = None
                pct = None

            entries.append(
                PrefillValidationEntry(
                    intent_id=item.intent_id,
                    mapping_id=item.mapping_id,
                    sheet=item.sheet,
                    cell=item.cell,
                    cell_ref=item.cell_ref,
                    metric=item.metric,
                    period=item.period,
                    status=PrefillValidationStatus.DISCREPANCY,
                    workbook_value=item.workbook_value,
                    sec_value=item.proposed_value,
                    difference=diff,
                    difference_pct=pct,
                    source_evidence=item.source,
                    reason=(
                        "Workbook/Bloomberg value disagrees with SEC; "
                        "recorded as discrepancy — not silently overwritten "
                        "(SEC is authoritative for resolution, not blind rewrite)"
                    ),
                    correction_applied=False,
                )
            )

        validated = sum(1 for e in entries if e.status == PrefillValidationStatus.VALIDATED)
        discrepancies = sum(
            1 for e in entries if e.status == PrefillValidationStatus.DISCREPANCY
        )
        skipped = sum(1 for e in entries if e.status == PrefillValidationStatus.SKIPPED)
        summary = (
            f"Prefill validation: {validated} VALIDATED, {discrepancies} DISCREPANCY, "
            f"{skipped} SKIPPED (no silent overwrites)."
        )
        return PrefillValidationReport(
            analysis_id=completion.analysis_id,
            ticker=completion.ticker,
            entries=entries,
            validated_count=validated,
            discrepancy_count=discrepancies,
            skipped_count=skipped,
            summary=summary,
        )
