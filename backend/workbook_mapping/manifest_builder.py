"""Manifest Builder — assemble WorkbookManifest from scan + classification."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from workbook_mapping.classifier import WorkbookClassifier
from workbook_mapping.models import (
    NamedRangeRecord,
    SuiteSheetFingerprint,
    WorkbookManifest,
    WorkbookProtection,
)
from workbook_mapping.scanner import WorkbookScanner
from workbook_mapping.statistics import StatisticsGenerator


ASSUMPTIONS = [
    "Computed used ranges are capped (400 rows × 80 cols) to ignore spurious openpyxl max_column=XFB.",
    "Blank cells inside used ranges are aggregated as Empty regions, not enumerated cell-by-cell.",
    "Every non-blank cell in the used range receives an explicit classification record.",
    "Annual IS/BS/CF period-body constants are Writable Input (P0 candidates); formulas are never writable.",
    "LQ standardized values are Historical Data / deferred P1 (writable=false until a future mapping).",
    "As-reported LQ sheets are Historical Data / Never for Mode A v0 mapping.",
    "Formula-driven sheets (Inputs, %, ratios, tax, leases, R&D, IC, FCF, Final Metrics) are Read-only.",
    "Output sheets (Enterprise Value, Expected Returns) classify formula cells as Output.",
    "Control values on annual sheets live in C1:C3; labels in A1:A3; CapIQ codes often in column B (hidden).",
    "Sheet name 'IC & NOPAT & ROIC ' includes a trailing space — exact match required.",
    "Filename version (v27.6) may differ from Template Version sheet (v27.7) — both recorded.",
    "Baseline manifest is built from the chosen ticker workbook; suite fingerprints validate structure parity.",
    "Downstream modules must consume this manifest and must not re-derive sheet roles from Excel.",
]


class ManifestBuilder:
    def __init__(self) -> None:
        self.scanner = WorkbookScanner()
        self.classifier = WorkbookClassifier()
        self.stats = StatisticsGenerator()

    def build(
        self,
        path: Path | str,
        *,
        baseline_ticker: str,
        suite_paths: dict[str, Path] | None = None,
    ) -> WorkbookManifest:
        path = Path(path)
        raw = self.scanner.scan(path)
        sheets = self.classifier.classify(raw)
        statistics = self.stats.generate(sheets, named_range_count=len(raw.named_ranges))

        edges = []
        for s in sheets:
            for dep, cnt in s.outbound_sheet_dependencies.items():
                edges.append({"from": s.name, "to": dep, "formula_ref_count": cnt})
        edges.sort(key=lambda e: -e["formula_ref_count"])

        named = [
            NamedRangeRecord(
                name=n["name"],
                attr_text=n.get("attr_text"),
                destinations=n.get("destinations") or [],
                broken=bool(n.get("broken")),
            )
            for n in raw.named_ranges
        ]

        wp = raw.workbook_protection
        protection = WorkbookProtection(
            workbook_locked=bool(wp.get("workbook_locked")),
            structure_locked=bool(wp.get("structure_locked")),
            windows_locked=bool(wp.get("windows_locked")),
            detail=wp.get("detail") or {},
        )

        m = re.search(r"v\d+\.\d+", path.name)
        filename_ver = m.group(0) if m else None

        suite_fps: list[SuiteSheetFingerprint] = []
        structure_identical = True
        if suite_paths:
            baseline_names = [s.name for s in sheets]
            baseline_roles = {s.name: s.role.value for s in sheets}
            baseline_wp = {s.name: s.write_policy.value for s in sheets}
            baseline_fp = {s.name: s.fill_priority.value for s in sheets}
            for ticker, spath in suite_paths.items():
                sraw = self.scanner.scan(spath)
                ssheets = self.classifier.classify(sraw)
                fp = SuiteSheetFingerprint(
                    ticker=ticker,
                    sheet_names=[s.name for s in ssheets],
                    roles={s.name: s.role.value for s in ssheets},
                    write_policies={s.name: s.write_policy.value for s in ssheets},
                    fill_priorities={s.name: s.fill_priority.value for s in ssheets},
                )
                suite_fps.append(fp)
                if fp.sheet_names != baseline_names:
                    structure_identical = False
                if fp.roles != baseline_roles or fp.write_policies != baseline_wp:
                    structure_identical = False
                if fp.fill_priorities != baseline_fp:
                    structure_identical = False
        else:
            suite_fps.append(
                SuiteSheetFingerprint(
                    ticker=baseline_ticker,
                    sheet_names=[s.name for s in sheets],
                    roles={s.name: s.role.value for s in sheets},
                    write_policies={s.name: s.write_policy.value for s in sheets},
                    fill_priorities={s.name: s.fill_priority.value for s in sheets},
                )
            )

        return WorkbookManifest(
            baseline_ticker=baseline_ticker,
            source_filename=raw.filename,
            source_sha256=raw.sha256,
            generated_at=datetime.now(timezone.utc).isoformat(),
            template_version_filename=filename_ver,
            template_version_sheet=raw.template_version_sheet,
            workbook_protection=protection,
            named_ranges=named,
            sheets=sheets,
            statistics=statistics,
            dependency_edges=edges,
            suite_fingerprints=suite_fps,
            suite_structure_identical=structure_identical if suite_paths else True,
            assumptions=list(ASSUMPTIONS),
        )


def build_manifest_from_path(
    path: Path | str,
    *,
    baseline_ticker: str = "AAPL",
    suite_paths: dict[str, Path] | None = None,
) -> WorkbookManifest:
    return ManifestBuilder().build(path, baseline_ticker=baseline_ticker, suite_paths=suite_paths)
