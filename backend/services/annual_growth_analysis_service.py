"""Company-specific prospective growth analysis for Annual Update valuation.

Anomaly detection is separated from assumption selection. Generic thresholds may
flag a series for investigation; they never become the selected rate, candidate,
or fallback. There is no hardcoded 8% (or any other generic substitute).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Callable

from models.annual_update import ValuationAssumptionAnalysis
from services.annual_period_service import detect_year_columns
from services.formula_utils import parse_cell_refs

ER_SHEET = "Expected Returns & Buybacks"
EV_SHEET = "Enterprise Value"
FM_SHEET = "Final Metrics"
INPUTS_SHEET = "Inputs"
INCOME_SHEET = "Income - GAAP"

# Anomaly-detection only. Never used as a selected / fallback / candidate rate.
_ANOMALY_HIGH_GROWTH = 0.25
_ANOMALY_VERY_HIGH_GROWTH = 0.30
_ANOMALY_DEEP_NEGATIVE = -0.10
_ANOMALY_HORIZON_GAP = 0.08
_ANOMALY_NEAR_ZERO_END_RATIO = 0.15
_ANOMALY_CAPEX_INTENSITY_MULTIPLE = 2.0
_ANOMALY_MARGIN_SHIFT = 0.05
_ANOMALY_DEPRESSED_START_RATIO = 0.50
_ANOMALY_ELEVATED_START_RATIO = 1.50
_ANOMALY_NI_STABLE_BAND = 0.35
_CLUSTER_MAX_WIDTH = 0.03
_SINGLE_OBS_KEEP_TOL = 0.01

KEEP = "KEEP_EXISTING"
ADJUST = "ADJUST"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


@dataclass
class _Decision:
    decision: str
    selected: float | None
    method: str
    lo: float | None
    hi: float | None
    conf: float
    evidence_center: float | None = None
    evidence_dispersion: float | None = None
    existing_distance_from_evidence: float | None = None
    materiality_assessment: str = ""
    decision_basis: str = ""


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if v != v:
            return None
        return float(v)
    if isinstance(v, str) and v.startswith("#"):
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _cagr(start: float | None, end: float | None, years: int) -> float | None:
    if start is None or end is None or years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:.1%}"


def _round_rate(v: float) -> float:
    """Avoid false precision: nearest 0.1 percentage point."""
    return round(v * 1000.0) / 1000.0


def _windows(values: list[float]) -> dict[str, float | None]:
    n = len(values)
    out: dict[str, float | None] = {"3y": None, "5y": None, "full": None}
    if n >= 4:
        out["3y"] = _cagr(values[-4], values[-1], 3)
    if n >= 6:
        out["5y"] = _cagr(values[-6], values[-1], 5)
    if n >= 2:
        out["full"] = _cagr(values[0], values[-1], n - 1)
    return out


def _fy_cols(ws, wb) -> list[tuple[str, int]]:
    cols = detect_year_columns(ws, wb)
    items = [(k, c) for k, c in cols.items() if str(k).startswith("FY")]
    items.sort(key=lambda x: x[0])
    return items


def _series_at_row(ws, row: int | None, fy_cols: list[tuple[str, int]]) -> list[tuple[str, float]]:
    if not row:
        return []
    out: list[tuple[str, float]] = []
    for fy, col in fy_cols:
        v = _num(ws.cell(row, col).value)
        if v is not None:
            out.append((fy, v))
    return out


def _row_by_label(ws, matcher: Callable[[str], bool], *, max_row: int = 130) -> int | None:
    for r in range(1, max_row + 1):
        lab = " ".join(str(ws.cell(r, 1).value or "").strip().lower().split())
        if lab and matcher(lab):
            return r
    return None


def _formula_refs(formula: Any, *, col: int, row: int) -> bool:
    if not isinstance(formula, str) or not formula.startswith("="):
        return False
    for ref in parse_cell_refs(formula):
        if ref["col"] == col and ref["row"] == row:
            return True
    return False


def _scan_formula_driver(ws, *, search_rows: list[int], candidates: dict[str, tuple[int, int]]) -> str | None:
    """Return the first candidate cell actually referenced by forecast formulas."""
    hits: list[str] = []
    for row in search_rows:
        for col in range(1, min((ws.max_column or 1), 24) + 1):
            val = ws.cell(row, col).value
            if not isinstance(val, str) or not val.startswith("="):
                continue
            for name, (c, r) in candidates.items():
                if _formula_refs(val, col=c, row=r) and name not in hits:
                    hits.append(name)
    return hits[0] if hits else None


def _tight_cluster(rates: list[float], *, max_width: float = _CLUSTER_MAX_WIDTH) -> list[float] | None:
    if len(rates) < 2:
        return None
    s = sorted(rates)
    best: list[float] | None = None
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            if s[j] - s[i] > max_width:
                break
            subset = s[i : j + 1]
            if best is None or len(subset) > len(best) or (
                len(subset) == len(best) and subset[-1] - subset[0] < best[-1] - best[0]
            ):
                best = subset
    if best and len(best) >= 2:
        return best
    return None


def _sign(x: float) -> int:
    if x > 1e-12:
        return 1
    if x < -1e-12:
        return -1
    return 0


def _same_observation(a: float | None, b: float | None) -> bool:
    """True when two figures are the same measured observation, not 'close enough to KEEP'."""
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= max(1e-4, 0.02 * scale)


def _persistent_sign(values: list[float]) -> int | None:
    signs = [_sign(v) for v in values if _sign(v) != 0]
    if not signs:
        return 0
    if all(s == signs[0] for s in signs):
        return signs[0]
    return None


def _mad(values: list[float], center: float) -> float:
    return float(median([abs(v - center) for v in values]))


def _classify_retention_defect(
    c5: float | None, annual: list[float]
) -> tuple[str | None, str]:
    """Classify an unusable retention identity. Does not repair the original formula.

    A factual/source; B formula/mapping; C valid unusual payout; D distorted
    denominator/base; E analyst/model issue.
    """
    if c5 is None:
        return None, ""
    plausible = -0.5 <= c5 <= 1.5
    if annual and len(annual) >= 3:
        abs_a = [abs(x) for x in annual]
        med = median(abs_a)
        worst = max(abs_a)
        if med > 0 and worst > max(5.0, 20.0 * med) and abs(c5) > 1.0:
            return (
                "D",
                "Average retention is dominated by a distorted annual ΔRE/EPS "
                f"observation ({worst:.0%} vs median magnitude {med:.1%}); the "
                "Inputs average-of-ratios formula is a fragile identity, not a "
                "usable retention ratio. Original formula is left unchanged.",
            )
        if plausible and worst > 1.0:
            return (
                "C",
                "Individual years show unusual payout/retention; the average remains "
                "within a usable identity for g = retention × ROE.",
            )
    if abs(c5) > 2.0:
        return (
            "D",
            f"Retention {c5:.1%} is not an economically usable retention ratio "
            "(distorted denominator/base). Original C5 formula is left unchanged.",
        )
    if not plausible:
        return (
            "E",
            "Retention lies outside a usable g = b × ROE identity (analyst/model "
            "fragility). Original formula is left unchanged.",
        )
    return None, ""


def _flag_rate_anomalies(prefix: str, windows: dict[str, float | None]) -> list[str]:
    flags: list[str] = []
    for name, g in windows.items():
        if g is None:
            continue
        if g > _ANOMALY_VERY_HIGH_GROWTH:
            flags.append(f"{prefix}_{name}_very_high")
        elif g > _ANOMALY_HIGH_GROWTH:
            flags.append(f"{prefix}_{name}_high")
        if g < _ANOMALY_DEEP_NEGATIVE:
            flags.append(f"{prefix}_{name}_deep_negative")
        elif g < 0:
            flags.append(f"{prefix}_{name}_negative")
    full, recent = windows.get("full"), windows.get("5y")
    if full is not None and recent is not None and abs(full - recent) > _ANOMALY_HORIZON_GAP:
        flags.append(f"{prefix}_horizon_divergence")
    return flags


def _base_effects(values: list[float], prefix: str) -> list[str]:
    if len(values) < 4:
        return []
    start, end = values[0], values[-1]
    recent = values[-5:] if len(values) >= 5 else values[-3:]
    pos_recent = [v for v in recent if v > 0]
    if not pos_recent:
        return [f"{prefix}_recent_nonpositive"]
    med = median(pos_recent)
    flags: list[str] = []
    if med > 0 and start > 0 and start < _ANOMALY_DEPRESSED_START_RATIO * med:
        flags.append(f"{prefix}_depressed_start")
    if med > 0 and start > _ANOMALY_ELEVATED_START_RATIO * med:
        flags.append(f"{prefix}_elevated_start")
    if med > 0 and abs(end) < _ANOMALY_NEAR_ZERO_END_RATIO * med:
        flags.append(f"{prefix}_collapsed_endpoint")
    return flags


def _usable_from_windows(
    windows: dict[str, float | None],
    *,
    distortions: list[str],
    prefix: str,
) -> dict[str, float]:
    """Drop windows whose endpoints make the CAGR unusable as a prospective rate."""
    usable: dict[str, float] = {}
    collapsed = any("collapsed_endpoint" in d for d in distortions if d.startswith(prefix))
    depressed = any("depressed_start" in d for d in distortions if d.startswith(prefix))
    elevated = any("elevated_start" in d for d in distortions if d.startswith(prefix))
    for name, g in windows.items():
        if g is None:
            continue
        if collapsed:
            continue
        if name == "full" and (depressed or elevated):
            continue
        usable[f"{prefix}_{name}"] = g
    return usable


@dataclass
class _Evidence:
    fy_labels: list[str] = field(default_factory=list)
    eps: list[tuple[str, float]] = field(default_factory=list)
    revenue: list[tuple[str, float]] = field(default_factory=list)
    operating_income: list[tuple[str, float]] = field(default_factory=list)
    ni: list[tuple[str, float]] = field(default_factory=list)
    da: list[tuple[str, float]] = field(default_factory=list)
    capex: list[tuple[str, float]] = field(default_factory=list)
    oe: list[tuple[str, float]] = field(default_factory=list)
    shares: list[tuple[str, float]] = field(default_factory=list)
    roe: list[tuple[str, float]] = field(default_factory=list)
    op_margin: list[tuple[str, float]] = field(default_factory=list)
    er_a11: float | None = None
    er_a11_formula: Any = None
    er_b5: float | None = None
    er_b5_formula: Any = None
    er_c5: float | None = None
    er_a14: float | None = None
    er_e14: float | None = None
    er_d17_d26: list[float | None] = field(default_factory=list)
    er_c17_formula: Any = None
    er_d17_formula: Any = None
    er_b14_formula: Any = None
    er_c14_formula: Any = None
    er_e14_formula: Any = None
    er_e17_formula: Any = None
    er_b8: float | None = None
    er_a2: float | None = None
    er_e2: float | None = None
    retention_annual: list[float] = field(default_factory=list)
    ev_b6: float | None = None
    ev_b6_formula: Any = None
    ev_c6: float | None = None
    ev_c6_formula: Any = None
    ev_b9_formula: Any = None
    ev_oe_driver: str | None = None
    ev_b41: float | None = None
    ev_b41_formula: Any = None
    ev_b42_formula: Any = None
    fm_l31: float | None = None
    fm_c31: float | None = None
    provenance: list[str] = field(default_factory=list)


class AnnualGrowthAnalysisService:
    """Build independent ER / OE / Graham analysis records from workbook evidence."""

    def collect(self, wb, wb_f) -> _Evidence:
        ev = _Evidence()
        fy_cols: list[tuple[str, int]] = []
        if INPUTS_SHEET in wb.sheetnames:
            fy_cols = _fy_cols(wb[INPUTS_SHEET], wb)
        if not fy_cols and INCOME_SHEET in wb.sheetnames:
            fy_cols = _fy_cols(wb[INCOME_SHEET], wb)
        ev.fy_labels = [fy for fy, _ in fy_cols]

        if INCOME_SHEET in wb.sheetnames:
            inc = wb[INCOME_SHEET]
            inc_cols = _fy_cols(inc, wb) or fy_cols
            eps_row = _row_by_label(
                inc,
                lambda lab: "diluted eps" in lab and "gaap" in lab and "cont" not in lab and "adj" not in lab,
            ) or 71
            rev_row = _row_by_label(inc, lambda lab: lab == "revenue" or lab.startswith("revenue ")) or 9
            oi_row = _row_by_label(inc, lambda lab: lab.startswith("operating income")) or 30
            sh_row = _row_by_label(inc, lambda lab: "diluted" in lab and "shares" in lab)
            ev.eps = _series_at_row(inc, eps_row, inc_cols)
            ev.revenue = _series_at_row(inc, rev_row, inc_cols)
            ev.operating_income = _series_at_row(inc, oi_row, inc_cols)
            if sh_row:
                ev.shares = _series_at_row(inc, sh_row, inc_cols)
            ev.provenance.append(f"{INCOME_SHEET} EPS/revenue/OI series")

        if INPUTS_SHEET in wb.sheetnames:
            inp = wb[INPUTS_SHEET]
            inp_cols = fy_cols or _fy_cols(inp, wb)
            ni_row = _row_by_label(inp, lambda lab: "consolidated net income" in lab or lab == "net income") or 38
            da_row = _row_by_label(inp, lambda lab: "depreciation" in lab) or 44
            cx_row = _row_by_label(inp, lambda lab: "capital expenditure" in lab) or 46
            ev.ni = _series_at_row(inp, ni_row, inp_cols)
            ev.da = _series_at_row(inp, da_row, inp_cols)
            ev.capex = _series_at_row(inp, cx_row, inp_cols)
            ni_map = dict(ev.ni)
            da_map = dict(ev.da)
            cx_map = dict(ev.capex)
            for fy in ev.fy_labels:
                ni = ni_map.get(fy)
                if ni is None:
                    continue
                oe = ni + (da_map.get(fy) or 0.0) + (cx_map.get(fy) or 0.0)
                ev.oe.append((fy, oe))
            ev.provenance.append(f"{INPUTS_SHEET} NI+D&A+CapEx owner-earnings identity")
            ret_row = _row_by_label(
                inp,
                lambda lab: "retained earnings per share/eps" in lab
                or "change in retained earnings per share/eps" in lab,
            )
            if ret_row:
                ev.retention_annual = [v for _, v in _series_at_row(inp, ret_row, inp_cols)]

        if FM_SHEET in wb.sheetnames:
            fm = wb[FM_SHEET]
            fm_cols = _fy_cols(fm, wb) or fy_cols
            roe_row = _row_by_label(fm, lambda lab: lab == "roe") or 4
            mar_row = _row_by_label(fm, lambda lab: "operating margin" in lab)
            ev.roe = _series_at_row(fm, roe_row, fm_cols)
            if mar_row:
                ev.op_margin = _series_at_row(fm, mar_row, fm_cols)
            ev.fm_l31 = _num(fm["L31"].value)
            ev.fm_c31 = _num(fm["C31"].value)
            ev.provenance.append(f"{FM_SHEET}!L31 is 10y EPS CAGR cross-check only; C31 is not 5y EPS or revenue")

        if ER_SHEET in wb.sheetnames:
            er = wb[ER_SHEET]
            ev.er_a11 = _num(er["A11"].value)
            ev.er_b5 = _num(er["B5"].value)
            ev.er_c5 = _num(er["C5"].value)
            ev.er_a14 = _num(er["A14"].value)
            ev.er_e14 = _num(er["E14"].value)
            ev.er_b8 = _num(er["B8"].value)
            ev.er_a2 = _num(er["A2"].value)
            ev.er_e2 = _num(er["E2"].value)
            ev.er_d17_d26 = [_num(er[f"D{r}"].value) for r in range(17, 27)]
            if ER_SHEET in wb_f.sheetnames:
                erf = wb_f[ER_SHEET]
                ev.er_a11_formula = erf["A11"].value
                ev.er_b5_formula = erf["B5"].value
                ev.er_c17_formula = erf["C17"].value
                ev.er_d17_formula = erf["D17"].value
                ev.er_b14_formula = erf["B14"].value
                ev.er_c14_formula = erf["C14"].value
                ev.er_e14_formula = erf["E14"].value
                ev.er_e17_formula = erf["E17"].value

        if EV_SHEET in wb.sheetnames:
            ews = wb[EV_SHEET]
            ev.ev_b6 = _num(ews["B6"].value)
            ev.ev_c6 = _num(ews["C6"].value)
            ev.ev_b41 = _num(ews["B41"].value)
            if EV_SHEET in wb_f.sheetnames:
                evf = wb_f[EV_SHEET]
                ev.ev_b6_formula = evf["B6"].value
                ev.ev_c6_formula = evf["C6"].value
                ev.ev_b9_formula = evf["B9"].value
                ev.ev_b41_formula = evf["B41"].value
                ev.ev_b42_formula = evf["B42"].value
                ev.ev_oe_driver = _scan_formula_driver(
                    evf,
                    search_rows=[8, 9, 10],
                    candidates={"C6": (3, 6), "B6": (2, 6)},
                )
        return ev

    def analyze(self, evidence: _Evidence) -> dict[str, ValuationAssumptionAnalysis]:
        return {
            "er": self._analyze_er(evidence),
            "oe": self._analyze_oe(evidence),
            "graham": self._analyze_graham(evidence),
        }

    def analyze_workbooks(self, wb, wb_f) -> dict[str, ValuationAssumptionAnalysis]:
        return self.analyze(self.collect(wb, wb_f))

    # ------------------------------------------------------------------ ER
    def _analyze_er(self, ev: _Evidence) -> ValuationAssumptionAnalysis:
        driver = self._er_formula_driver(ev)
        if driver == "A11":
            existing, source, grain = ev.er_a11, f"{ER_SHEET}!A11", "sustainable_g_retention_x_roe"
        elif driver == "B5":
            existing, source, grain = ev.er_b5, f"{ER_SHEET}!B5", "eps_growth_assumption"
        else:
            existing = ev.er_a11 if ev.er_a11 is not None else ev.er_b5
            source = f"{ER_SHEET}!A11" if ev.er_a11 is not None else f"{ER_SHEET}!B5"
            grain = "inferred_without_forecast_formula"
            driver = source.split("!")[-1] if source else None

        eps_vals = [v for _, v in ev.eps]
        rev_vals = [v for _, v in ev.revenue]
        oi_vals = [v for _, v in ev.operating_income]
        eps_w = _windows(eps_vals)
        rev_w = _windows(rev_vals)
        oi_w = _windows(oi_vals)
        anomalies = _flag_rate_anomalies("eps", eps_w) + _flag_rate_anomalies("rev", rev_w)
        distortions = _base_effects(eps_vals, "eps") + _base_effects(rev_vals, "rev")
        if ev.op_margin and len(ev.op_margin) >= 2:
            m0, m1 = ev.op_margin[0][1], ev.op_margin[-1][1]
            if abs(m1 - m0) > _ANOMALY_MARGIN_SHIFT:
                anomalies.append("operating_margin_shift")

        usable = {}
        usable.update(_usable_from_windows(eps_w, distortions=distortions, prefix="eps"))
        usable.update(_usable_from_windows(rev_w, distortions=distortions, prefix="rev"))
        usable.update(_usable_from_windows(oi_w, distortions=distortions, prefix="oi"))
        # g = retention × ROE is the existing A11 identity — keep it as an
        # observation, not an independent range point that would tautologically
        # contain the current assumption.
        shares_cagr = _windows([v for _, v in ev.shares]).get("full")
        if shares_cagr is not None and abs(shares_cagr) >= 0.01:
            anomalies.append("material_share_count_change")

        ret_class, ret_note = _classify_retention_defect(ev.er_c5, ev.retention_annual)
        mechanism_unusable = False
        if ret_class in {"D", "E"}:
            distortions.append(f"retention_defect_{ret_class}")
            mechanism_unusable = True
        if ev.er_a11 is not None and abs(ev.er_a11) > 1.0:
            distortions.append("sustainable_growth_identity_unusable")
            mechanism_unusable = True
        if ret_note:
            distortions.append(ret_note)

        current_eps = eps_vals[-1] if eps_vals else None
        d17 = next((x for x in ev.er_d17_d26 if x is not None), None)
        implied_g = (ev.er_c5 * ev.er_a14) if ev.er_c5 is not None and ev.er_a14 is not None else None
        hist = {
            "eps_series": ev.eps,
            "eps_3y_cagr": eps_w["3y"],
            "eps_5y_cagr": eps_w["5y"],
            "eps_10y_cagr": eps_w["full"],
            "revenue_cagr": rev_w["full"],
            "revenue_5y_cagr": rev_w["5y"],
            "oi_cagr": oi_w["full"],
            "oi_5y_cagr": oi_w["5y"],
            "roe_latest": ev.er_a14,
            "retention": ev.er_c5,
            "retention_annual": ev.retention_annual,
            "retention_defect_class": ret_class,
            "retention_x_roe": implied_g,
            "book_value_start": ev.er_b8,
            "current_price": ev.er_a2,
            "max_pe10": ev.er_e2,
            "projected_eps_path": ev.er_d17_d26,
            "current_eps": current_eps,
            "d17_starting_projected_eps": d17,
            "eps_recent_levels": ev.eps[-4:],
            "shares_cagr": shares_cagr,
            "workbook_b5_display": ev.er_b5,
            "original_expected_return_e14": ev.er_e14,
            "original_mechanics": {
                "retention_c5": ev.er_c5,
                "roe_a14": ev.er_a14,
                "sustainable_g_a11": ev.er_a11,
                "g_identity": "retention × ROE",
                "bv_path": ev.er_c17_formula,
                "eps_path": ev.er_d17_formula,
                "eps_in_10y": ev.er_b14_formula,
                "terminal_price": ev.er_c14_formula,
                "expected_return": ev.er_e14_formula,
                "dividends": ev.er_e17_formula,
            },
        }
        recent = {
            "eps_recent_levels": ev.eps[-4:],
            "eps_5y_cagr": eps_w["5y"],
            "oi_5y_cagr": oi_w["5y"],
            "revenue_5y_cagr": rev_w["5y"],
        }
        historical_existing = None
        if driver == "B5" and _same_observation(existing, eps_w.get("full")):
            historical_existing = eps_w.get("full")
        dec = self._conservative_policy(
            self._decide(
                existing,
                usable,
                extra_blockers=[],
                existing_excluded_keys=(),
                historical_existing=historical_existing,
                mechanism_unusable=mechanism_unusable,
            ),
            existing,
            usable,
        )
        rationale = self._er_rationale(existing, driver, hist, distortions, dec)
        return ValuationAssumptionAnalysis(
            metric="expected_return_growth",
            existing_assumption=existing,
            existing_assumption_source=source,
            existing_assumption_grain=grain,
            actual_formula_driver=f"{ER_SHEET}!{driver}" if driver else None,
            historical_observations=hist,
            recent_observations=recent,
            normalization_adjustments=[
                d for d in distortions if "depressed" in d or "elevated" in d or "collapsed" in d
            ],
            distortions_identified=distortions,
            anomalies=anomalies,
            prospective_range_low=dec.lo,
            prospective_range_high=dec.hi,
            selected_prospective_rate=dec.selected,
            selection_method=dec.method,
            rationale=rationale,
            evidence=self._evidence_lines(hist, distortions, usable),
            provenance=list(ev.provenance) + [f"ER forecast formulas C17={ev.er_c17_formula!r} D17={ev.er_d17_formula!r}"],
            confidence=dec.conf,
            valuation_impact="Expected Return E14 path; originals unchanged; HAP parallel model preserves ROE vs growth roles",
            decision=dec.decision,
            evidence_center=dec.evidence_center,
            evidence_dispersion=dec.evidence_dispersion,
            existing_distance_from_evidence=dec.existing_distance_from_evidence,
            materiality_assessment=dec.materiality_assessment,
            decision_basis=dec.decision_basis,
        )

    def _er_formula_driver(self, ev: _Evidence) -> str | None:
        for formula in (ev.er_c17_formula, ev.er_d17_formula):
            if _formula_refs(formula, col=1, row=11):
                return "A11"
            if _formula_refs(formula, col=2, row=5):
                return "B5"
        if isinstance(ev.er_a11_formula, str) and ev.er_a11_formula.startswith("="):
            return "A11"
        return "A11" if ev.er_a11 is not None else ("B5" if ev.er_b5 is not None else None)

    def _er_rationale(self, existing, driver, hist, distortions, dec: _Decision) -> str:
        recent_eps = hist.get("eps_recent_levels") or []
        if recent_eps:
            recent_txt = ", ".join(f"{fy} {v:.2f}" for fy, v in recent_eps)
        else:
            recent_txt = "n/a"
        d17 = hist.get("d17_starting_projected_eps")
        d17_txt = f"{d17:.2f}" if isinstance(d17, (int, float)) else "n/a"
        cur = hist.get("current_eps")
        cur_txt = f"{cur:.2f}" if isinstance(cur, (int, float)) else "n/a"
        parts = [
            f"The workbook Expected Return projection is driven by {driver} "
            f"({_pct(existing)}; grain: retention × ROE when A11 is the driver), not by the B5 display "
            f"({_pct(hist.get('workbook_b5_display'))}) unless a forecast formula actually references B5.",
            f"Long-term EPS CAGR is {_pct(hist.get('eps_10y_cagr'))}; recent 5-year EPS CAGR is "
            f"{_pct(hist.get('eps_5y_cagr'))}; recent EPS levels are {recent_txt}.",
            f"Revenue CAGR {_pct(hist.get('revenue_cagr'))} (5y {_pct(hist.get('revenue_5y_cagr'))}); "
            f"operating-income CAGR {_pct(hist.get('oi_cagr'))} (5y {_pct(hist.get('oi_5y_cagr'))}).",
            f"ROE {_pct(hist.get('roe_latest'))} and retention {_pct(hist.get('retention'))} imply "
            f"g = {_pct(hist.get('retention_x_roe'))}. Starting projected EPS D17="
            f"{d17_txt} vs current EPS {cur_txt}.",
        ]
        defect = hist.get("retention_defect_class")
        if defect:
            parts.append(f"Retention defect class {defect}.")
        if distortions:
            parts.append("Distortions: " + ", ".join(str(d) for d in distortions if len(str(d)) < 180) + ".")
        parts.append(dec.decision_basis or self._decision_sentence(dec))
        if dec.materiality_assessment:
            parts.append(dec.materiality_assessment)
        return " ".join(parts)

    # ------------------------------------------------------------------ OE / EV
    def _analyze_oe(self, ev: _Evidence) -> ValuationAssumptionAnalysis:
        grain_b6, grain_c6 = self._oe_grains(ev)
        driver_cell = ev.ev_oe_driver
        if driver_cell is None:
            if grain_c6 == "annualized_growth_rate":
                driver_cell = "C6"
            elif ev.ev_c6 is not None:
                driver_cell = "C6"
            else:
                driver_cell = None
        existing = ev.ev_c6 if driver_cell == "C6" else (ev.ev_b6 if driver_cell == "B6" else ev.ev_c6)
        source = f"{EV_SHEET}!{driver_cell}" if driver_cell else None
        grain = grain_c6 if driver_cell == "C6" else grain_b6

        oe_vals = [v for _, v in ev.oe]
        ni_vals = [v for _, v in ev.ni]
        oi_vals = [v for _, v in ev.operating_income]
        rev_vals = [v for _, v in ev.revenue]
        capex_vals = [v for _, v in ev.capex]
        oe_w = _windows(oe_vals)
        ni_w = _windows(ni_vals)
        oi_w = _windows(oi_vals)
        rev_w = _windows(rev_vals)

        decomp = []
        ni_map, da_map, cx_map, oe_map = dict(ev.ni), dict(ev.da), dict(ev.capex), dict(ev.oe)
        for fy in ev.fy_labels:
            decomp.append(
                {
                    "fy": fy,
                    "ni": ni_map.get(fy),
                    "da": da_map.get(fy),
                    "capex": cx_map.get(fy),
                    "oe": oe_map.get(fy),
                }
            )

        distortions = _base_effects(oe_vals, "oe") + _base_effects(ni_vals, "ni")
        if oe_vals and oe_vals[-1] <= 0:
            distortions.append("oe_collapsed_endpoint")
            distortions.append("oe_nonpositive_endpoint")
        anomalies = _flag_rate_anomalies("oe", oe_w) + _flag_rate_anomalies("ni", ni_w)
        capex_spike, intensity_note = self._capex_spike(ni_vals, capex_vals)
        if capex_spike:
            distortions.append("oe_reinvestment_capex_spike")
            anomalies.append("capex_intensity_spike")
        ni_stable = self._series_stable(ni_vals)
        oe_collapsed = any("oe_collapsed_endpoint" in d or "oe_nonpositive" in d for d in distortions)
        if capex_spike and oe_vals:
            prior_oe = [v for v in oe_vals[:-2] if v > 0]
            if prior_oe and oe_vals[-1] < 0.5 * median(prior_oe):
                oe_collapsed = True
                distortions.append("oe_endpoint_halved_after_reinvestment_spike")
        base_unusable = False
        if capex_spike and ni_stable and oe_collapsed:
            distortions.append("oe_forecast_base_distorted_by_reinvestment")
            distortions.append("DISTORTED_BASE")
            base_unusable = True
        elif oe_collapsed and ni_stable:
            distortions.append("oe_endpoint_not_an_earnings_power_base")
            distortions.append("DISTORTED_BASE")
            base_unusable = True
        if intensity_note:
            distortions.append(intensity_note)

        usable = {}
        usable.update(_usable_from_windows(ni_w, distortions=distortions, prefix="ni"))
        usable.update(_usable_from_windows(oi_w, distortions=distortions, prefix="oi"))
        usable.update(_usable_from_windows(rev_w, distortions=distortions, prefix="rev"))
        # OE CAGRs only if the series itself is a usable earnings-power path.
        if not base_unusable:
            usable.update(_usable_from_windows(oe_w, distortions=distortions, prefix="oe"))

        blockers = ["distorted_oe_forecast_base"] if base_unusable else []
        hist = {
            "oe_total_change_b6": ev.ev_b6,
            "oe_total_change_grain": grain_b6,
            "oe_annualized_c6": ev.ev_c6,
            "oe_annualized_grain": grain_c6,
            "oe_decomposition": decomp,
            "oe_3y_cagr": oe_w["3y"],
            "oe_5y_cagr": oe_w["5y"],
            "oe_10y_cagr": oe_w["full"],
            "ni_cagr": ni_w["full"],
            "ni_5y_cagr": ni_w["5y"],
            "oi_cagr": oi_w["full"],
            "oi_5y_cagr": oi_w["5y"],
            "revenue_cagr": rev_w["full"],
            "revenue_5y_cagr": rev_w["5y"],
            "forecast_formula_b9": ev.ev_b9_formula,
        }
        recent = {
            "oe_recent": ev.oe[-4:],
            "ni_recent": ev.ni[-4:],
            "capex_recent": ev.capex[-4:],
            "oi_recent": ev.operating_income[-4:],
        }
        dec = self._decide(
            existing,
            usable,
            extra_blockers=blockers,
            existing_excluded_keys=("oe_full", "oe_5y", "oe_3y") if base_unusable else (),
            historical_existing=oe_w.get("full") if _same_observation(existing, oe_w.get("full")) else None,
        )
        if base_unusable:
            dec.decision = INSUFFICIENT
            dec.selected = None
            dec.method = "insufficient_evidence_distorted_forecast_base"
            dec.conf = min(dec.conf, 0.45)
            dec.decision_basis = (
                "The OE forecast base is distorted; HAP does not invent a replacement rate "
                "and does not treat the prospective range as a decision boundary."
            )
        dec = self._conservative_policy(dec, existing, usable)
        rationale = self._oe_rationale(existing, driver_cell, hist, distortions, dec)
        return ValuationAssumptionAnalysis(
            metric="owner_earnings_growth",
            existing_assumption=existing,
            existing_assumption_source=source,
            existing_assumption_grain=grain or "annualized_growth_rate",
            actual_formula_driver=f"{EV_SHEET}!{driver_cell}" if driver_cell else None,
            historical_observations=hist,
            recent_observations=recent,
            normalization_adjustments=[
                "decomposed OE into NI, D&A, CapEx",
                "treated B6 as total historical change, not the forecast rate",
            ]
            + [d for d in distortions if "capex" in d or "base" in d],
            distortions_identified=distortions,
            anomalies=anomalies,
            prospective_range_low=dec.lo,
            prospective_range_high=dec.hi,
            selected_prospective_rate=dec.selected,
            selection_method=dec.method,
            rationale=rationale,
            evidence=self._evidence_lines(hist, distortions, usable),
            provenance=list(ev.provenance) + [f"EV B9={ev.ev_b9_formula!r} C6={ev.ev_c6_formula!r} B6={ev.ev_b6_formula!r}"],
            confidence=dec.conf,
            valuation_impact="Enterprise Value / Margin of Safety path using C6; originals unchanged",
            decision=dec.decision,
            evidence_center=dec.evidence_center,
            evidence_dispersion=dec.evidence_dispersion,
            existing_distance_from_evidence=dec.existing_distance_from_evidence,
            materiality_assessment=dec.materiality_assessment,
            decision_basis=dec.decision_basis,
        )

    def _oe_grains(self, ev: _Evidence) -> tuple[str, str]:
        b6_grain = "unknown"
        c6_grain = "unknown"
        c6f = ev.ev_c6_formula
        b6f = ev.ev_b6_formula
        if isinstance(c6f, str) and c6f.startswith("=") and _formula_refs(c6f, col=2, row=6):
            if "^" in c6f.replace(" ", "") or "^(1/" in c6f.replace(" ", "") or "1/9" in c6f.replace(" ", ""):
                c6_grain = "annualized_growth_rate"
                b6_grain = "total_historical_change"
            else:
                c6_grain = "derived_from_b6"
        if isinstance(b6f, str) and b6f.startswith("=") and "/" in b6f and "-1" in b6f.replace(" ", ""):
            b6_grain = "total_historical_change"
        if c6_grain == "unknown" and ev.ev_c6 is not None:
            c6_grain = "annualized_growth_rate"
        if b6_grain == "unknown" and ev.ev_b6 is not None:
            b6_grain = "total_historical_change" if ev.ev_c6 is not None else "unverified_level"
        return b6_grain, c6_grain

    def _capex_spike(self, ni: list[float], capex: list[float]) -> tuple[bool, str | None]:
        n = min(len(ni), len(capex))
        if n < 4:
            return False, None
        intensities = []
        for i in range(n):
            denom = abs(ni[i]) if abs(ni[i]) > 1e-9 else None
            if denom:
                intensities.append(abs(capex[i]) / denom)
        if len(intensities) < 4:
            return False, None
        prior = intensities[:-2] if len(intensities) > 4 else intensities[:-1]
        last = intensities[-1]
        med_prior = median(prior) if prior else None
        if med_prior and med_prior > 0 and last > _ANOMALY_CAPEX_INTENSITY_MULTIPLE * med_prior:
            return True, f"capex_ni_intensity_end={last:.2f}_vs_median_prior={med_prior:.2f}"
        return False, None

    def _series_stable(self, values: list[float]) -> bool:
        pos = [v for v in values if v is not None]
        if len(pos) < 3:
            return False
        med = median(abs(v) for v in pos)
        if med <= 0:
            return False
        return abs(pos[-1] - med) / med <= _ANOMALY_NI_STABLE_BAND

    def _oe_rationale(self, existing, driver, hist, distortions, dec: _Decision) -> str:
        parts = [
            f"The Enterprise Value forecast formula uses {driver or 'an unidentified driver'} "
            f"(existing annualized assumption {_pct(existing)}). "
            f"B6 ({_pct(hist.get('oe_total_change_b6'))}) is {hist.get('oe_total_change_grain')} "
            f"and is not treated as the prospective annual rate.",
            f"OE identity NI+D&A+CapEx: 10y OE CAGR {_pct(hist.get('oe_10y_cagr'))}, "
            f"5y {_pct(hist.get('oe_5y_cagr'))}, 3y {_pct(hist.get('oe_3y_cagr'))}. "
            f"NI CAGR {_pct(hist.get('ni_cagr'))} (5y {_pct(hist.get('ni_5y_cagr'))}); "
            f"operating income {_pct(hist.get('oi_cagr'))} (5y {_pct(hist.get('oi_5y_cagr'))}); "
            f"revenue {_pct(hist.get('revenue_cagr'))}.",
        ]
        if distortions:
            parts.append("Distortions: " + ", ".join(distortions) + ".")
        parts.append(dec.decision_basis or self._decision_sentence(dec, existing=existing))
        if dec.materiality_assessment:
            parts.append(dec.materiality_assessment)
        return " ".join(parts)

    # ------------------------------------------------------------------ Graham
    def _analyze_graham(self, ev: _Evidence) -> ValuationAssumptionAnalysis:
        driver = None
        if _formula_refs(ev.ev_b42_formula, col=2, row=41):
            driver = "B41"
        existing = ev.ev_b41 if ev.ev_b41 is not None else ev.fm_l31
        source = f"{EV_SHEET}!B41" if ev.ev_b41 is not None else (f"{FM_SHEET}!L31" if ev.fm_l31 is not None else None)
        grain = "graham_eps_growth_input"

        eps_vals = [v for _, v in ev.eps]
        rev_vals = [v for _, v in ev.revenue]
        oi_vals = [v for _, v in ev.operating_income]
        eps_w = _windows(eps_vals)
        rev_w = _windows(rev_vals)
        oi_w = _windows(oi_vals)
        anomalies = _flag_rate_anomalies("eps", eps_w) + _flag_rate_anomalies("rev", rev_w)
        distortions = _base_effects(eps_vals, "eps")
        # Explicitly ignore Final Metrics C31 — it is not 5y EPS and not revenue.
        usable = {}
        usable.update(_usable_from_windows(eps_w, distortions=distortions, prefix="eps"))
        usable.update(_usable_from_windows(rev_w, distortions=distortions, prefix="rev"))
        usable.update(_usable_from_windows(oi_w, distortions=distortions, prefix="oi"))
        # Do not tautologically keep 10y CAGR solely because it is the existing input.
        usable.pop("eps_full", None)

        direction = None
        if len(eps_vals) >= 2:
            direction = "P" if eps_vals[-1] >= eps_vals[0] else "N"
        hist = {
            "eps_series": ev.eps,
            "eps_3y_cagr": eps_w["3y"],
            "eps_5y_cagr": eps_w["5y"],
            "eps_10y_cagr": eps_w["full"],
            "eps_direction": direction,
            "revenue_cagr": rev_w["full"],
            "revenue_5y_cagr": rev_w["5y"],
            "oi_cagr": oi_w["full"],
            "oi_5y_cagr": oi_w["5y"],
            "fm_l31_crosscheck": ev.fm_l31,
            "fm_c31_ignored": ev.fm_c31,
            "shares_cagr": _windows([v for _, v in ev.shares]).get("full"),
        }
        recent = {"eps_recent": ev.eps[-4:], "eps_5y_cagr": eps_w["5y"], "oi_5y_cagr": oi_w["5y"]}
        historical_existing = eps_w.get("full") if _same_observation(existing, eps_w.get("full")) else None
        dec = self._conservative_policy(
            self._decide(
                existing,
                usable,
                extra_blockers=[],
                historical_existing=historical_existing,
            ),
            existing,
            usable,
        )
        rationale = (
            f"Graham uses {source or 'an unidentified growth input'} ({_pct(existing)}) in the existing "
            f"intrinsic-value formula (driver {driver or 'B41 if present'}). "
            f"True 10-year EPS CAGR from the EPS series is {_pct(eps_w['full'])}; true 5-year EPS CAGR is "
            f"{_pct(eps_w['5y'])}. Final Metrics C31 ({_pct(ev.fm_c31)}) is not a 5-year EPS CAGR and is not "
            f"revenue growth; it is ignored. Revenue CAGR {_pct(rev_w['full'])}; operating-income CAGR "
            f"{_pct(oi_w['full'])}; EPS direction {direction}. "
            + ("Distortions: " + ", ".join(distortions) + ". " if distortions else "")
            + (dec.decision_basis or self._decision_sentence(dec, existing=existing))
        )
        return ValuationAssumptionAnalysis(
            metric="graham_eps_growth",
            existing_assumption=existing,
            existing_assumption_source=source,
            existing_assumption_grain=grain,
            actual_formula_driver=f"{EV_SHEET}!{driver}" if driver else source,
            historical_observations=hist,
            recent_observations=recent,
            normalization_adjustments=["ignored Final Metrics C31 as 5y EPS/revenue"],
            distortions_identified=distortions,
            anomalies=anomalies,
            prospective_range_low=dec.lo,
            prospective_range_high=dec.hi,
            selected_prospective_rate=dec.selected,
            selection_method=dec.method,
            rationale=rationale,
            evidence=self._evidence_lines(hist, distortions, usable),
            provenance=list(ev.provenance) + ["Graham B42 formula references B41; EPS series from Income - GAAP"],
            confidence=dec.conf,
            valuation_impact="Graham intrinsic / entry price; originals unchanged",
            decision=dec.decision,
            evidence_center=dec.evidence_center,
            evidence_dispersion=dec.evidence_dispersion,
            existing_distance_from_evidence=dec.existing_distance_from_evidence,
            materiality_assessment=dec.materiality_assessment,
            decision_basis=dec.decision_basis,
        )

    # ------------------------------------------------------------------ decision
    def _conservative_policy(self, dec: _Decision, existing: float | None, usable: dict) -> _Decision:
        """Keep statistical evidence as one input. Do not adopt a CAGR, or a more optimistic rate, as the alternative."""
        note = (
            " Historical CAGR is evidence, not an automatic prospective growth assumption."
            " Management guidance is evidence and is not adopted automatically."
            " When an alternative is justified it is the more conservative supportable rate."
        )
        if dec.decision == INSUFFICIENT:
            dec.decision_basis = ((dec.decision_basis or "") + " HAP did not manufacture an alternative." + note).strip()
            return dec
        if dec.decision != ADJUST or dec.selected is None:
            dec.decision_basis = ((dec.decision_basis or "") + note).strip()
            return dec
        recent = [
            float(v)
            for key, v in usable.items()
            if ("3y" in key or "5y" in key) and isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        if existing is not None and dec.selected > existing + 0.005:
            lower = [v for v in recent if v < existing]
            if not lower:
                dec.decision = INSUFFICIENT
                dec.selected = None
                dec.method = "insufficient_evidence_no_conservative_alternative"
                dec.conf = min(dec.conf, 0.4)
                dec.decision_basis = (
                    "Independent evidence is more optimistic than the base model, and no lower recent "
                    "observation supports a conservative alternative. The base model is preserved."
                    + note
                )
                return dec
            dec.selected = _round_rate(min(lower))
            dec.method = "conservative_recent_evidence"
        elif recent and existing is not None:
            conservative = min(recent)
            if conservative + 0.01 < float(dec.selected) and conservative < existing:
                dec.selected = _round_rate(conservative)
                dec.method = "conservative_recent_evidence"
        dec.decision_basis = ((dec.decision_basis or "") + note).strip()
        if dec.method == "conservative_recent_evidence":
            dec.decision_basis += f" Selected conservative rate {_pct(dec.selected)}."
        return dec

    def _decide(
        self,
        existing: float | None,
        usable: dict[str, float],
        *,
        extra_blockers: list[str],
        existing_excluded_keys: tuple[str, ...] = (),  # noqa: ARG002 — recorded by callers, not a KEEP tautology
        historical_existing: float | None = None,
        mechanism_unusable: bool = False,
    ) -> _Decision:
        rates = list(usable.values())
        lo = min(rates) if rates else None
        hi = max(rates) if rates else None
        center = float(median(rates)) if rates else None
        dispersion = _mad(rates, center) if rates and center is not None else None
        distance = (existing - center) if existing is not None and center is not None else None

        def pack(
            decision: str,
            selected: float | None,
            method: str,
            conf: float,
            *,
            basis: str,
            materiality: str,
        ) -> _Decision:
            return _Decision(
                decision=decision,
                selected=selected,
                method=method,
                lo=lo,
                hi=hi,
                conf=conf,
                evidence_center=center,
                evidence_dispersion=dispersion,
                existing_distance_from_evidence=distance,
                materiality_assessment=materiality,
                decision_basis=basis,
            )

        rng = f"{_pct(lo)}–{_pct(hi)}" if lo is not None and hi is not None else "unavailable"
        if extra_blockers:
            return pack(
                INSUFFICIENT,
                None,
                "insufficient_evidence_distorted_forecast_base",
                0.4,
                basis="The forecast base is distorted; HAP does not invent a replacement rate.",
                materiality="Materiality is not evaluated against a usable earnings-power base.",
            )
        if not rates:
            return pack(
                INSUFFICIENT,
                None,
                "insufficient_evidence_no_independent_observations",
                0.35,
                basis="No independent observations are available to evaluate the existing assumption.",
                materiality="Insufficient evidence; no materiality comparison is possible.",
            )

        if existing is not None and len(rates) == 1:
            if _same_observation(existing, rates[0]):
                return pack(
                    KEEP,
                    existing,
                    "single_observation_consistent_with_existing",
                    0.7,
                    basis=(
                        f"A single independent observation {_pct(rates[0])} is the same measured "
                        f"figure as the existing assumption {_pct(existing)}; HAP keeps it."
                    ),
                    materiality="One observation cannot justify replacing the analyst assumption.",
                )
            return pack(
                INSUFFICIENT,
                None,
                "insufficient_evidence_single_observation_not_enough_to_replace",
                0.45,
                basis=(
                    f"Only one independent observation {_pct(rates[0])} is available; that is not "
                    f"enough evidence to replace the existing assumption {_pct(existing)}."
                ),
                materiality="Insufficient independent evidence; no override.",
            )

        cluster = _tight_cluster(rates)
        earnings = [v for k, v in usable.items() if k.startswith("eps")]
        operating = [v for k, v in usable.items() if k.startswith(("rev", "oi", "ni"))]
        recent = [v for k, v in usable.items() if "3y" in k or "5y" in k]
        recent_eps = [v for k, v in usable.items() if k.startswith("eps") and ("3y" in k or "5y" in k)]
        recent_op = [
            v for k, v in usable.items()
            if k.startswith(("rev", "oi", "ni")) and ("3y" in k or "5y" in k)
        ]
        all_sign = _persistent_sign(rates)
        exist_sign = _sign(existing) if existing is not None else 0
        inside = existing is not None and lo is not None and hi is not None and lo <= existing <= hi
        hist_match = _same_observation(existing, historical_existing)
        five_y = usable.get("eps_5y")
        earnings_flipped = (
            hist_match
            and five_y is not None
            and exist_sign != 0
            and _sign(five_y) != 0
            and exist_sign != _sign(five_y)
        )
        same_earnings_regime = hist_match and exist_sign != 0 and not earnings_flipped and (
            not earnings or _persistent_sign(earnings) in {None, 0, exist_sign}
        )
        contradicted = False
        contradiction_notes: list[str] = []
        if existing is not None and exist_sign != 0:
            re_sign = _persistent_sign(recent_eps)
            ro_sign = _persistent_sign(recent_op if recent_op else operating)
            if (
                re_sign not in {None, 0}
                and re_sign != exist_sign
                and ro_sign not in {None, 0}
                and ro_sign != exist_sign
            ):
                contradicted = True
                contradiction_notes.append(
                    "persistent recent earnings windows and operating indicators disagree in sign "
                    "with the existing assumption"
                )
            elif all_sign not in {None, 0} and all_sign != exist_sign:
                contradicted = True
                contradiction_notes.append(
                    "every independent observation with a sign disagrees with the existing assumption"
                )

        nearest = None
        gap_nearest = None
        if existing is not None and rates:
            nearest = min(rates, key=lambda r: abs(r - existing))
            gap_nearest = abs(existing - nearest)
        in_neighborhood = (
            existing is not None
            and gap_nearest is not None
            and dispersion is not None
            and dispersion > 0
            and gap_nearest <= dispersion
            and exist_sign != 0
            and all_sign in {None, 0, exist_sign}
        )

        keep_support: list[str] = []
        if inside:
            keep_support.append("existing sits inside the independent evidence range")
        if same_earnings_regime:
            keep_support.append(
                "existing is itself a measured long-term earnings observation and recent EPS remains in the same regime"
            )
        if in_neighborhood:
            keep_support.append(
                "existing is within the evidence dispersion of an independent observation and shares the evidence sign"
            )

        materiality = (
            f"Evidence center {_pct(center)}, dispersion (MAD) {_pct(dispersion)}, "
            f"existing distance from center {_pct(distance)}, independent range {rng}. "
            f"Nearest independent observation {_pct(nearest)} (gap {_pct(gap_nearest)}). "
            "The range is an evidence summary, not an acceptance/rejection interval. "
            "Materiality is judged from sign persistence, earnings-regime continuity, "
            "and distance relative to evidence dispersion — not a fixed percentage-point or "
            "percent-of-range tolerance."
        )

        def adjust_pack(selected: float, method: str, basis: str) -> _Decision:
            return pack(ADJUST, selected, method, 0.7, basis=basis, materiality=materiality)

        if mechanism_unusable:
            if cluster:
                selected = _round_rate(median(cluster))
                return adjust_pack(
                    selected,
                    "median_of_corroborating_cluster",
                    (
                        f"The original sustainable-growth identity is economically unusable "
                        f"(existing {_pct(existing)}). Independent evidence supports replacing "
                        f"that mechanism with {_pct(selected)} for HAP_ANALYSIS only. "
                        "Original workbook formulas are not repaired."
                    ),
                )
            return pack(
                INSUFFICIENT,
                None,
                "insufficient_evidence_unusable_mechanism_no_coherent_alternative",
                0.4,
                basis=(
                    f"The original sustainable-growth identity is unusable ({_pct(existing)}), "
                    "and independent evidence is not tight enough to construct a replacement."
                ),
                materiality=materiality,
            )

        if contradicted:
            if cluster:
                selected = _round_rate(median(cluster))
                return adjust_pack(
                    selected,
                    "median_of_corroborating_cluster",
                    (
                        f"The existing assumption {_pct(existing)} conflicts materially with "
                        f"independent evidence ({'; '.join(contradiction_notes)}). The difference "
                        "cannot reasonably be explained by normal evidence dispersion. HAP selects "
                        f"{_pct(selected)} from the corroborating cluster, not because the figure "
                        f"merely sits outside range {rng}."
                    ),
                )
            return pack(
                INSUFFICIENT,
                None,
                "insufficient_evidence_contradicted_without_tight_alternative",
                0.45,
                basis=(
                    f"The existing assumption {_pct(existing)} is economically contradicted, but "
                    "the independent evidence is not clustered tightly enough to justify a "
                    "specific replacement rate."
                ),
                materiality=materiality,
            )

        if existing is not None and keep_support and not contradicted:
            return pack(
                KEEP,
                existing,
                "existing_supported_by_economic_evidence",
                0.8,
                basis=(
                    f"Although the independent evidence-derived range is {rng}, the existing "
                    f"assumption {_pct(existing)} remains consistent with the company's evidence "
                    f"({'; '.join(keep_support)}). The difference is not sufficiently material, "
                    "given the dispersion in the evidence, to justify replacing the analyst assumption."
                ),
                materiality=materiality,
            )

        if existing is not None and cluster and not (min(cluster) <= existing <= max(cluster)):
            selected = _round_rate(median(cluster))
            return adjust_pack(
                selected,
                "median_of_corroborating_cluster",
                (
                    f"The existing assumption {_pct(existing)} is economically unsupported by the "
                    f"corroborating evidence cluster {_pct(min(cluster))}–{_pct(max(cluster))}, and "
                    "the gap is material relative to that cluster. HAP selects "
                    f"{_pct(selected)}. The independent range {rng} is not by itself the reason."
                ),
            )

        if existing is None and cluster:
            selected = _round_rate(median(cluster))
            return adjust_pack(
                selected,
                "median_of_corroborating_cluster",
                f"No existing assumption is present; HAP uses the corroborating cluster median {_pct(selected)}.",
            )

        return pack(
            INSUFFICIENT,
            None,
            "insufficient_evidence_no_tight_alternative",
            0.5,
            basis=(
                f"Independent evidence supports a prospective range of {rng}, but it is not "
                f"sufficient to replace the existing assumption {_pct(existing)} with an invented rate."
            ),
            materiality=materiality,
        )

    def _decision_sentence(self, dec: _Decision, *, existing: float | None = None) -> str:
        if dec.decision_basis:
            return dec.decision_basis
        rng = f"{_pct(dec.lo)}–{_pct(dec.hi)}" if dec.lo is not None and dec.hi is not None else "unavailable"
        if dec.decision == KEEP:
            return (
                f"The existing assumption {_pct(existing)} remains consistent with the evidence "
                f"(range {rng} is a summary, not a hard bound). HAP keeps it "
                f"(selection_method={dec.method})."
            )
        if dec.decision == ADJUST:
            return (
                f"The existing assumption {_pct(existing)} is economically unsupported and the "
                f"difference is material relative to the evidence. HAP selects {_pct(dec.selected)} "
                f"using {dec.method}."
            )
        return (
            f"Independent evidence supports a prospective range of {rng}, but it is not sufficient "
            f"to replace the existing assumption {_pct(existing)}."
        )

    def _evidence_lines(self, hist: dict[str, Any], distortions: list[str], usable: dict[str, float]) -> list[str]:
        lines = [f"{k}={_pct(v) if isinstance(v, float) else v}" for k, v in usable.items()]
        lines.extend(distortions)
        for key in (
            "eps_10y_cagr",
            "eps_5y_cagr",
            "revenue_cagr",
            "oi_cagr",
            "ni_cagr",
            "oe_10y_cagr",
        ):
            if key in hist and hist[key] is not None:
                lines.append(f"{key}={_pct(hist[key])}")
        return lines
