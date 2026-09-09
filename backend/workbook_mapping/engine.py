"""M3 Write Intent Engine — CFM + mapping spec → validated write intents (no Excel I/O)."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from canonical_model.company import CompanyFinancialModel
from canonical_model.primitives import FinancialPoint
from workbook_mapping.mapping_builder import build_mapping_specification
from workbook_mapping.mapping_schema import MappingEntry, MappingSpecification, TimeDimension
from workbook_mapping.models import CellClass, FillPriority, WritePolicy

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "workbook_mapping" / "Workbook_Manifest.json"
)
DEFAULT_MAPPING_JSON = (
    Path(__file__).resolve().parents[2] / "docs" / "workbook_mapping" / "CFM_Workbook_Mapping.json"
)

TRANSFORM_DIVIDE_1E6 = "divide_by_1_000_000"
TRANSFORM_FORMAT_FY = "format_fy_token"


class IntentDecision(str, Enum):
    """Top-level M3 decision consumed by future Fill (M4)."""

    WRITE = "WRITE"
    SKIP = "SKIP"
    BLOCK = "BLOCK"


class WriteIntentValidationError(ValueError):
    """Raised when the write-intent batch cannot be accepted."""


class WriteIntent(BaseModel):
    """Explicit plan to write (or refuse) one value into one Industrial Template cell."""

    intent_id: str
    mapping_id: str
    sheet: str
    cell: str
    metric: str
    period: str
    value: Any | None = None
    source: str
    source_document: str | None = None
    transformation: str | None = None
    confidence: float | None = None
    existing_cell_classification: str | None = None
    write_policy_result: str
    decision: IntentDecision
    reason: str
    cfm_path: str
    unit: str | None = None
    data_type: str | None = None
    fill_priority: str | None = None
    original_value_preview: str | None = None
    xbrl_tag: str | None = None
    filing_type: str | None = None
    accession_number: str | None = None

    @property
    def cell_ref(self) -> str:
        return f"{self.sheet}!{self.cell}"


class WriteIntentReport(BaseModel):
    """Machine-readable M3 artifact (`write_intents.json`)."""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "M3"
    mapping_schema_version: str | None = None
    intents: list[WriteIntent] = Field(default_factory=list)
    write_count: int = 0
    skip_count: int = 0
    block_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    unmapped_cfm_paths_with_data: list[str] = Field(default_factory=list)


def load_mapping_specification(
    *,
    mapping_json: Path | None = None,
    manifest_path: Path | None = None,
    workbook_path: Path | None = None,
) -> MappingSpecification:
    """Load mapping spec from checked-in JSON, or rebuild from manifest.

    Always merges deterministic Inputs tax/PE10/current_data mappings.
    When ``workbook_path`` is provided, period column FY tokens are aligned to
    the workbook's detected fiscal window (supports rolling FY2017–FY2026, etc.).
    """
    from workbook_mapping.explicit_mappings import ANNUAL_PERIOD_COLS, ANNUAL_PERIOD_FY_TOKENS
    from workbook_mapping.inputs_mappings import inputs_mappings
    from workbook_mapping.mapping_schema import PeriodColumnMap

    json_path = mapping_json or DEFAULT_MAPPING_JSON
    if json_path.exists():
        spec = MappingSpecification.model_validate(json.loads(json_path.read_text(encoding="utf-8")))
    else:
        spec = build_mapping_specification(manifest_path or DEFAULT_MANIFEST_PATH)

    fy_tokens = list(ANNUAL_PERIOD_FY_TOKENS)
    if workbook_path is not None and Path(workbook_path).exists():
        try:
            from services.annual_period_service import detect_workbook_years

            detected = detect_workbook_years(Path(workbook_path))
            ordered = sorted(
                ((fy, col) for fy, col in detected.items() if str(fy).startswith("FY")),
                key=lambda item: item[1],
            )
            if len(ordered) >= 2:
                fy_tokens = [fy for fy, _ in ordered[: len(ANNUAL_PERIOD_COLS)]]
                while len(fy_tokens) < len(ANNUAL_PERIOD_COLS):
                    last = int(fy_tokens[-1].replace("FY", ""))
                    fy_tokens.append(f"FY{last + 1}")
        except Exception:  # noqa: BLE001
            fy_tokens = list(ANNUAL_PERIOD_FY_TOKENS)

    cols = {col: fy for col, fy in zip(ANNUAL_PERIOD_COLS, fy_tokens, strict=False)}
    # Prefer Income - GAAP map column letters when present, but replace FY tokens.
    for pcm in spec.period_column_maps:
        if pcm.sheet in {"Income - GAAP", "Balance Sheet - Standardized", "Inputs"} and pcm.columns:
            letters = sorted(pcm.columns.keys(), key=lambda c: (len(c), c))
            pcm.columns = {
                letter: fy_tokens[i] if i < len(fy_tokens) else f"FY{2016 + i}"
                for i, letter in enumerate(letters[: len(ANNUAL_PERIOD_COLS)])
            }

    # Ensure Inputs FY column map (same window as annual statements).
    if not any(p.sheet == "Inputs" for p in spec.period_column_maps):
        for pcm in spec.period_column_maps:
            if pcm.sheet == "Income - GAAP" and pcm.columns:
                cols = dict(pcm.columns)
                break
        else:
            cols = {col: fy for col, fy in zip(ANNUAL_PERIOD_COLS, fy_tokens, strict=False)}
        spec.period_column_maps.append(
            PeriodColumnMap(
                sheet="Inputs",
                header_row=1,
                date_row=2,
                columns=cols,
            )
        )

    # Keep mapping entry column lists; period tokens come from period_column_maps.
    existing_ids = {m.mapping_id for m in spec.mappings}
    for entry in inputs_mappings():
        if entry.mapping_id not in existing_ids:
            spec.mappings.append(entry)
            existing_ids.add(entry.mapping_id)
    return spec



def load_manifest_index(manifest_path: Path | None = None) -> dict[str, Any]:
    """Load Workbook_Manifest.json and index cells by (sheet, address)."""
    path = manifest_path or DEFAULT_MANIFEST_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    sheets: dict[str, dict[str, Any]] = {}
    for sheet in data.get("sheets") or []:
        name = sheet["name"]
        sheets[name] = sheet
        for cell in sheet.get("cells") or []:
            cells[(name, cell["address"])] = cell
    return {
        "raw": data,
        "sheets": sheets,
        "cells": cells,
        "workbook_protection": data.get("workbook_protection") or {},
    }


def _period_map_for_sheet(mapping: MappingSpecification, sheet: str) -> dict[str, str]:
    for pcm in mapping.period_column_maps:
        if pcm.sheet == sheet:
            return dict(pcm.columns)
    return {}


def _ensure_template_year_metadata(
    model: CompanyFinancialModel,
    mapping: MappingSpecification,
) -> None:
    """Derive Start/End Year controls from the period map when CFM metadata lacks them."""
    if mapping.period_column_maps:
        cols = mapping.period_column_maps[0].columns
        ordered = [cols[c] for c in sorted(cols.keys()) if cols.get(c)]
        if ordered:
            model.metadata.setdefault("template_start_year", ordered[0])
            model.metadata.setdefault("template_end_year", ordered[-1])


def _resolve_cfm_scalar(model: CompanyFinancialModel, cfm_path: str) -> Any | None:
    if cfm_path == "ticker":
        return model.ticker
    if cfm_path.startswith("metadata."):
        key = cfm_path.split(".", 1)[1]
        return model.metadata.get(key)
    if cfm_path.startswith("inputs."):
        field = cfm_path.split(".", 1)[1]
        bridge = getattr(model, "inputs", None)
        if bridge is None:
            return None
        if field == "tax_unit_flag":
            return bridge.tax_unit_flag
        return bridge.scalar_for(field)
    if cfm_path.startswith("market_data."):
        field = cfm_path.split(".", 1)[1]
        return getattr(model.market_data, field, None)
    return None


def _resolve_cfm_point(
    model: CompanyFinancialModel,
    cfm_path: str,
    period: str,
) -> FinancialPoint | None:
    parts = cfm_path.split(".")
    if len(parts) != 2:
        return None
    section, field = parts
    if section == "inputs":
        bridge = getattr(model, "inputs", None)
        if bridge is None:
            return None
        try:
            series = bridge.series_for(field)
        except AttributeError:
            return None
        return series.point_for(period)
    statement = getattr(model, section, None)
    if statement is None or not hasattr(statement, "series_for"):
        return None
    try:
        series = statement.series_for(field)
    except AttributeError:
        return None
    return series.point_for(period)


def _normalize_fy_token(value: Any) -> str:
    text = str(value).strip().replace(" ", "").upper()
    if text.startswith("FY") and len(text) >= 6:
        return f"FY{text[-4:]}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 4:
        return f"FY{digits}"
    return text


def _apply_transformation(value: Any, transformation: str | None) -> Any:
    if value is None or not transformation:
        return value
    if transformation == TRANSFORM_DIVIDE_1E6:
        if not isinstance(value, (int, float)):
            raise WriteIntentValidationError(
                f"Cannot apply {TRANSFORM_DIVIDE_1E6} to non-numeric value {value!r}"
            )
        return value / 1_000_000.0
    if transformation == TRANSFORM_FORMAT_FY:
        return _normalize_fy_token(value)
    return value


def map_model_to_write_intents(
    model: CompanyFinancialModel,
    mapping: MappingSpecification,
    *,
    manifest_index: dict[str, Any] | None = None,
    source_document: str | None = None,
) -> WriteIntentReport:
    """
    Pure M3 API: CFM + mapping + manifest → write intents.

    Does not open or modify any Excel workbook.
    Period tokens come only from the mapping period_column_map (no silent remap).
    """
    _ensure_template_year_metadata(model, mapping)
    index = manifest_index if manifest_index is not None else load_manifest_index()
    sheets = index["sheets"]
    cells = index["cells"]
    protection = index.get("workbook_protection") or {}

    intents: list[WriteIntent] = []
    warnings: list[str] = []
    seen_targets: dict[tuple[str, str], WriteIntent] = {}
    default_source = source_document or str(
        model.metadata.get("custom_run_source") or "CompanyFinancialModel"
    )

    for entry in sorted(mapping.mappings, key=lambda m: (m.write_priority, m.mapping_id)):
        period_cols = _period_map_for_sheet(mapping, entry.sheet)
        sheet_meta = sheets.get(entry.sheet)

        if sheet_meta is None:
            for col in entry.columns:
                intents.append(
                    _make_intent(
                        entry,
                        f"{col}{entry.row}",
                        period="n/a",
                        value=None,
                        decision=IntentDecision.BLOCK,
                        write_policy_result="sheet_missing",
                        reason=f"Sheet '{entry.sheet}' missing from Workbook_Manifest",
                        classification=None,
                        source=default_source,
                    )
                )
            continue

        sheet_policy = str(sheet_meta.get("write_policy") or "")
        # Inputs bridge sinks are completion targets despite legacy Formula/Read-only policy.
        inputs_sink = entry.sheet == "Inputs" and (
            (entry.notes or "").startswith("inputs_sink")
            or entry.fill_priority == "P0"
        )
        effective_sheet_meta = sheet_meta
        if inputs_sink:
            sheet_policy = WritePolicy.HYBRID.value
            effective_sheet_meta = dict(sheet_meta)
            effective_sheet_meta["write_policy"] = WritePolicy.HYBRID.value
            effective_sheet_meta["fill_priority"] = FillPriority.P0.value
        if sheet_policy == WritePolicy.READ_ONLY.value and not inputs_sink:
            for col in entry.columns:
                intents.append(
                    _make_intent(
                        entry,
                        f"{col}{entry.row}",
                        period=period_cols.get(col, "n/a"),
                        value=None,
                        decision=IntentDecision.BLOCK,
                        write_policy_result="read_only_sheet",
                        reason=f"Sheet '{entry.sheet}' write_policy is Read-only",
                        classification=None,
                        source=default_source,
                    )
                )
            continue

        if protection.get("workbook_locked") or protection.get("structure_locked"):
            for col in entry.columns:
                intents.append(
                    _make_intent(
                        entry,
                        f"{col}{entry.row}",
                        period=period_cols.get(col, "control"),
                        value=None,
                        decision=IntentDecision.BLOCK,
                        write_policy_result="workbook_protected",
                        reason="Workbook structure/protection flagged in manifest",
                        classification=None,
                        source=default_source,
                    )
                )
            continue

        if entry.time_dimension == TimeDimension.CONTROL:
            col = entry.columns[0]
            addr = f"{col}{entry.row}"
            raw = _resolve_cfm_scalar(model, entry.cfm_path)
            period = "control"
            if entry.cfm_path.endswith("template_start_year") and period_cols:
                period = period_cols.get(sorted(period_cols.keys())[0], "control")
            elif entry.cfm_path.endswith("template_end_year") and period_cols:
                period = period_cols.get(sorted(period_cols.keys())[-1], "control")
            intents.append(
                _classify_value_intent(
                    entry=entry,
                    addr=addr,
                    period=period,
                    raw_value=raw,
                    cells=cells,
                    sheet_meta=effective_sheet_meta,
                    sheet_policy=sheet_policy,
                    source=default_source,
                    seen_targets=seen_targets,
                    warnings=warnings,
                )
            )
            continue

        if entry.time_dimension == TimeDimension.POINT:
            col = entry.columns[0]
            addr = f"{col}{entry.row}"
            raw = _resolve_cfm_scalar(model, entry.cfm_path)
            source = default_source
            if entry.cfm_path == "inputs.current_price":
                source = (
                    getattr(model.inputs, "current_price_source", None)
                    or "market_internet"
                )
            elif entry.notes and "bloomberg" in entry.notes:
                source = "bloomberg_custom_run"
            elif entry.notes and "sec_edgar" in entry.notes:
                source = "sec_edgar_10k"
            intents.append(
                _classify_value_intent(
                    entry=entry,
                    addr=addr,
                    period="current",
                    raw_value=raw,
                    cells=cells,
                    sheet_meta=effective_sheet_meta,
                    sheet_policy=sheet_policy,
                    source=source,
                    seen_targets=seen_targets,
                    warnings=warnings,
                )
            )
            continue

        for col in entry.columns:
            addr = f"{col}{entry.row}"
            fy_token = period_cols.get(col)
            if not fy_token:
                intents.append(
                    _make_intent(
                        entry,
                        addr,
                        period="unknown",
                        value=None,
                        decision=IntentDecision.BLOCK,
                        write_policy_result="missing_period_map",
                        reason=f"No FY token for column {col} on {entry.sheet}",
                        classification=None,
                        source=default_source,
                    )
                )
                continue

            point = _resolve_cfm_point(model, entry.cfm_path, fy_token)
            raw = point.value if point is not None else None
            source = (point.source if point and point.source else None) or default_source
            provenance = point.provenance if point else None
            intents.append(
                _classify_value_intent(
                    entry=entry,
                    addr=addr,
                    period=fy_token,
                    raw_value=raw,
                    cells=cells,
                    sheet_meta=effective_sheet_meta,
                    sheet_policy=sheet_policy,
                    source=source,
                    seen_targets=seen_targets,
                    warnings=warnings,
                    confidence=point.confidence if point is not None else None,
                    xbrl_tag=provenance.xbrl_tag if provenance else None,
                    filing_type=provenance.filing_type if provenance else None,
                    accession_number=provenance.accession_number if provenance else None,
                    source_document=(
                        provenance.source_document if provenance and provenance.source_document else default_source
                    ),
                )
            )

    mapped_paths = {m.cfm_path for m in mapping.mappings}
    unmapped_with_data: list[str] = []
    for unmapped in mapping.unmapped_cfm_metrics:
        if unmapped.cfm_path in mapped_paths or "." not in unmapped.cfm_path:
            continue
        section, field = unmapped.cfm_path.split(".", 1)
        statement = getattr(model, section, None)
        if statement is None or not hasattr(statement, "series_for"):
            continue
        try:
            series = statement.series_for(field)
        except AttributeError:
            continue
        if series.points:
            unmapped_with_data.append(unmapped.cfm_path)
            warnings.append(
                f"CFM has data for unmapped path {unmapped.cfm_path} "
                f"({len(series.points)} points); not guessed"
            )

    report = WriteIntentReport(
        analysis_id=model.analysis_id,
        ticker=model.ticker,
        mapping_schema_version=mapping.schema_version,
        intents=intents,
        warnings=warnings,
        unmapped_cfm_paths_with_data=unmapped_with_data,
    )
    _recount(report)
    return report


def _classify_value_intent(
    *,
    entry: MappingEntry,
    addr: str,
    period: str,
    raw_value: Any,
    cells: dict[tuple[str, str], dict[str, Any]],
    sheet_meta: dict[str, Any],
    sheet_policy: str,
    source: str,
    seen_targets: dict[tuple[str, str], WriteIntent],
    warnings: list[str],
    confidence: float | None = None,
    xbrl_tag: str | None = None,
    filing_type: str | None = None,
    accession_number: str | None = None,
    source_document: str | None = None,
) -> WriteIntent:
    cell_meta = cells.get((entry.sheet, addr))
    classification = cell_meta.get("classification") if cell_meta else None
    preview = cell_meta.get("value_preview") if cell_meta else None
    formula = cell_meta.get("formula") if cell_meta else None

    if cell_meta is not None:
        if classification == CellClass.FORMULA.value or formula:
            return _make_intent(
                entry,
                addr,
                period=period,
                value=None,
                decision=IntentDecision.BLOCK,
                write_policy_result="formula_cell",
                reason=f"Target {entry.sheet}!{addr} is a formula cell; never WRITE",
                classification=classification,
                source=source,
                original_preview=preview,
                confidence=confidence,
                xbrl_tag=xbrl_tag,
                filing_type=filing_type,
                accession_number=accession_number,
                source_document=source_document,
            )
        if classification == CellClass.PROTECTED.value:
            return _make_intent(
                entry,
                addr,
                period=period,
                value=None,
                decision=IntentDecision.BLOCK,
                write_policy_result="protected_cell",
                reason=f"Target {entry.sheet}!{addr} is Protected in the manifest",
                classification=classification,
                source=source,
                original_preview=preview,
                confidence=confidence,
                source_document=source_document,
            )
        if classification and classification != CellClass.WRITABLE_INPUT.value:
            return _make_intent(
                entry,
                addr,
                period=period,
                value=None,
                decision=IntentDecision.BLOCK,
                write_policy_result=f"disallowed:{classification}",
                reason=(
                    f"Target {entry.sheet}!{addr} classification is {classification}, "
                    "not Writable Input"
                ),
                classification=classification,
                source=source,
                original_preview=preview,
                confidence=confidence,
                source_document=source_document,
            )
        if cell_meta.get("writable") is False:
            return _make_intent(
                entry,
                addr,
                period=period,
                value=None,
                decision=IntentDecision.BLOCK,
                write_policy_result="not_writable",
                reason=f"Target {entry.sheet}!{addr} is not writable per manifest",
                classification=classification,
                source=source,
                original_preview=preview,
                confidence=confidence,
                source_document=source_document,
            )
    else:
        fill_priority = sheet_meta.get("fill_priority")
        if fill_priority == "Never" or sheet_policy == WritePolicy.READ_ONLY.value:
            return _make_intent(
                entry,
                addr,
                period=period,
                value=None,
                decision=IntentDecision.BLOCK,
                write_policy_result="structurally_invalid",
                reason=(
                    f"Target {entry.sheet}!{addr} absent from manifest and sheet is not writable"
                ),
                classification=None,
                source=source,
                confidence=confidence,
                source_document=source_document,
            )
        classification = CellClass.WRITABLE_INPUT.value

    if raw_value is None:
        return _make_intent(
            entry,
            addr,
            period=period,
            value=None,
            decision=IntentDecision.SKIP,
            write_policy_result="null_cfm_value",
            reason=f"CFM has no value for {entry.cfm_path} @ {period}; null skips write",
            classification=classification,
            source=source,
            original_preview=preview,
            confidence=confidence,
            source_document=source_document,
        )

    try:
        value = _apply_transformation(raw_value, entry.transformation)
    except WriteIntentValidationError as exc:
        return _make_intent(
            entry,
            addr,
            period=period,
            value=None,
            decision=IntentDecision.BLOCK,
            write_policy_result="transformation_failed",
            reason=str(exc),
            classification=classification,
            source=source,
            original_preview=preview,
            confidence=confidence,
            source_document=source_document,
        )

    if entry.transformation == TRANSFORM_FORMAT_FY:
        value = _normalize_fy_token(value)

    intent = _make_intent(
        entry,
        addr,
        period=period,
        value=value,
        decision=IntentDecision.WRITE,
        write_policy_result=f"writable:{sheet_policy or 'Hybrid'}",
        reason=f"Mapped {entry.cfm_path} ({period}) → {entry.sheet}!{addr} via {entry.mapping_id}",
        classification=classification,
        source=source,
        original_preview=preview,
        confidence=confidence if confidence is not None else 0.9,
        xbrl_tag=xbrl_tag,
        filing_type=filing_type,
        accession_number=accession_number,
        source_document=source_document,
    )

    key = (entry.sheet, addr)
    prior = seen_targets.get(key)
    if prior is not None and prior.decision == IntentDecision.WRITE:
        if prior.value != intent.value:
            conflict_reason = (
                f"Ambiguous conflict at {entry.sheet}!{addr}: "
                f"{prior.mapping_id}={prior.value!r} vs {entry.mapping_id}={intent.value!r}"
            )
            warnings.append(conflict_reason)
            prior.decision = IntentDecision.BLOCK
            prior.write_policy_result = "ambiguous_conflict"
            prior.reason = conflict_reason
            prior.value = None
            return _make_intent(
                entry,
                addr,
                period=period,
                value=None,
                decision=IntentDecision.BLOCK,
                write_policy_result="ambiguous_conflict",
                reason=conflict_reason,
                classification=classification,
                source=source,
                original_preview=preview,
                confidence=confidence,
                source_document=source_document,
            )
        warnings.append(
            f"Duplicate identical intent for {entry.sheet}!{addr} "
            f"({prior.mapping_id} and {entry.mapping_id})"
        )
        return _make_intent(
            entry,
            addr,
            period=period,
            value=None,
            decision=IntentDecision.SKIP,
            write_policy_result="duplicate_identical",
            reason="Duplicate identical target; keeping first WRITE intent",
            classification=classification,
            source=source,
            original_preview=preview,
            confidence=confidence,
            source_document=source_document,
        )

    if intent.decision == IntentDecision.WRITE:
        seen_targets[key] = intent
    return intent


def _make_intent(
    entry: MappingEntry,
    addr: str,
    *,
    period: str,
    value: Any,
    decision: IntentDecision,
    write_policy_result: str,
    reason: str,
    classification: str | None,
    source: str,
    original_preview: str | None = None,
    confidence: float | None = None,
    xbrl_tag: str | None = None,
    filing_type: str | None = None,
    accession_number: str | None = None,
    source_document: str | None = None,
) -> WriteIntent:
    return WriteIntent(
        intent_id=f"{entry.mapping_id}:{addr}",
        mapping_id=entry.mapping_id,
        sheet=entry.sheet,
        cell=addr,
        metric=entry.metric_name,
        period=period,
        value=value,
        source=source,
        source_document=source_document or source,
        transformation=entry.transformation,
        confidence=confidence,
        existing_cell_classification=classification,
        write_policy_result=write_policy_result,
        decision=decision,
        reason=reason,
        cfm_path=entry.cfm_path,
        unit=entry.unit,
        data_type=entry.data_type,
        fill_priority=entry.fill_priority,
        original_value_preview=original_preview,
        xbrl_tag=xbrl_tag,
        filing_type=filing_type,
        accession_number=accession_number,
    )


def _recount(report: WriteIntentReport) -> None:
    report.write_count = sum(1 for i in report.intents if i.decision == IntentDecision.WRITE)
    report.skip_count = sum(1 for i in report.intents if i.decision == IntentDecision.SKIP)
    report.block_count = sum(1 for i in report.intents if i.decision == IntentDecision.BLOCK)


def validate_write_intents(report: WriteIntentReport) -> list[WriteIntent]:
    """
    Validate the intent batch. Ambiguous conflicts hard-fail.
    Returns WRITE intents only (M4 will consume these later).
    """
    conflicts = [
        i for i in report.intents if i.write_policy_result == "ambiguous_conflict"
    ]
    if conflicts:
        details = "; ".join(c.reason for c in conflicts[:5])
        raise WriteIntentValidationError(
            f"Write-intent validation failed with {len(conflicts)} ambiguous conflict(s): {details}"
        )

    for intent in report.intents:
        if intent.decision != IntentDecision.WRITE:
            continue
        if (
            intent.existing_cell_classification
            and intent.existing_cell_classification != CellClass.WRITABLE_INPUT.value
        ):
            raise WriteIntentValidationError(
                f"WRITE intent {intent.intent_id} has classification "
                f"{intent.existing_cell_classification}"
            )
        if intent.value is None:
            raise WriteIntentValidationError(f"WRITE intent {intent.intent_id} has null value")

    return [i for i in report.intents if i.decision == IntentDecision.WRITE]
