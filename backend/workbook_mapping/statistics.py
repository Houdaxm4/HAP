"""Statistics Generator for Workbook Manifest."""

from __future__ import annotations

from collections import Counter

from workbook_mapping.models import (
    CellClass,
    SheetClassification,
    WorkbookStatistics,
)


class StatisticsGenerator:
    def generate(self, sheets: list[SheetClassification], named_range_count: int) -> WorkbookStatistics:
        class_counts: Counter[str] = Counter()
        roles: Counter[str] = Counter()
        policies: Counter[str] = Counter()

        writable = formula = read_only = protected = 0
        historical = output = helper = reserved = named_range_cells = 0
        empty = 0
        nonblank = 0
        merged = tables = charts = dvs = cfs = 0
        hidden_rows = hidden_cols = 0

        for s in sheets:
            roles[s.role.value] += 1
            policies[s.write_policy.value] += 1
            nonblank += s.metrics.nonblank_cells
            empty += s.metrics.blank_in_used_range
            formula += s.metrics.formula_cells
            merged += len(s.objects.merged_cells)
            tables += len([t for t in s.objects.tables if "name" in t])
            charts += len([c for c in s.objects.charts if "error" not in c])
            dvs += len(s.objects.data_validations)
            cfs += sum(int(x.get("rule_count") or 0) for x in s.objects.conditional_formatting)
            hidden_rows += len(s.objects.hidden_rows)
            hidden_cols += len(s.objects.hidden_columns)

            for cell in s.cells:
                class_counts[cell.classification.value] += 1
                if cell.writable:
                    writable += 1
                if cell.classification == CellClass.FORMULA:
                    pass  # counted via metrics too
                if cell.classification == CellClass.READ_ONLY:
                    read_only += 1
                if cell.classification == CellClass.PROTECTED:
                    protected += 1
                if cell.classification == CellClass.HISTORICAL_DATA:
                    historical += 1
                if cell.classification == CellClass.OUTPUT:
                    output += 1
                if cell.classification == CellClass.HELPER:
                    helper += 1
                if cell.classification == CellClass.RESERVED:
                    reserved += 1
                if cell.named_ranges:
                    named_range_cells += 1
                if cell.classification == CellClass.FORMULA:
                    pass

            for region in s.regions:
                if region.classification == CellClass.EMPTY:
                    class_counts[CellClass.EMPTY.value] += region.cell_count

        # Prefer cell-record formula count for consistency with classification
        formula_classified = class_counts.get(CellClass.FORMULA.value, 0) + class_counts.get(
            CellClass.OUTPUT.value, 0
        )

        return WorkbookStatistics(
            worksheets=len(sheets),
            used_cells_nonblank=nonblank,
            writable_cells=writable,
            formula_cells=formula_classified,
            read_only_cells=read_only,
            protected_cells=protected,
            historical_data_cells=historical,
            output_cells=output,
            helper_cells=helper,
            empty_cells_in_used_ranges=empty,
            reserved_cells=reserved,
            named_range_cells=named_range_cells,
            merged_ranges=merged,
            named_ranges=named_range_count,
            tables=tables,
            charts=charts,
            data_validation_rules=dvs,
            conditional_formatting_rules=cfs,
            hidden_rows=hidden_rows,
            hidden_columns=hidden_cols,
            classification_counts=dict(class_counts),
            sheets_by_role=dict(roles),
            sheets_by_write_policy=dict(policies),
        )
