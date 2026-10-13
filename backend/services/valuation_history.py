"""Small, pure statistics for the valuation checks: which years of a history are off, whether EPS follows a steady trend,
and an EPS growth rate that is not skewed by extraordinary years. No workbook access here, so every rule is easy to test.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

# A year is "off" when it is far from the typical year in both senses: many robust standard deviations AND a large share of the median.
OFF_Z = 2.5
OFF_RELATIVE = 0.35
MAX_OFF_SHARE = 0.30            # more than this share of the years off means the whole history is noisy, not a few years
MIN_YEARS = 6                   # fewer years than this cannot support a trend or a trimmed average

# EPS: a steady trend has a log-linear fit this good; an extraordinary year sits this far (in logs) from the trend of the others
TREND_R2 = 0.60
EXTRAORDINARY_LOG = 0.25
EXTRAORDINARY_Z = 2.5
SKEW_MATERIAL = 0.02            # the endpoint growth rate must differ from the robust one by at least two points to be called skewed


def _mad(values: list[float]) -> float:
    med = statistics.median(values)
    return statistics.median(abs(v - med) for v in values) * 1.4826


def off_years(series: dict[str, float], *, z: float = OFF_Z, relative: float = OFF_RELATIVE) -> list[str]:
    """Years whose value is far from the typical (median) year: beyond `z` robust standard deviations and `relative` of the median."""
    if len(series) < MIN_YEARS:
        return []
    values = list(series.values())
    med = statistics.median(values)
    scale = _mad(values)
    out = []
    for year, value in series.items():
        dev = abs(value - med)
        if dev > z * max(scale, 1e-12) and dev >= relative * max(abs(med), 1e-12):
            out.append(year)
    return out


def trimmed_mean(series: dict[str, float], drop: list[str]) -> float | None:
    kept = [v for k, v in series.items() if k not in drop]
    return statistics.mean(kept) if kept else None


@dataclass
class LogLinear:
    growth: float               # exp(slope) - 1, per year
    r2: float
    years_used: int


def loglinear(series: dict[str, float], exclude: list[str] | None = None) -> LogLinear | None:
    """Log-linear (constant growth) fit through the positive values; None when there are too few or any value is not positive."""
    exclude = exclude or []
    pts = [(i, v) for i, (k, v) in enumerate(series.items()) if k not in exclude]
    if len(pts) < 3 or any(v <= 0 for _i, v in pts):
        return None
    xs = [float(i) for i, _v in pts]
    ys = [math.log(v) for _i, v in pts]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return LogLinear(math.exp(slope) - 1.0, r2, len(pts))


@dataclass
class EpsTrend:
    reasonable: bool
    r2: float | None
    growth: float | None
    reason: str


def eps_trend(eps: dict[str, float]) -> EpsTrend:
    """Does EPS follow a steady trend? Needs enough years, all positive, and a log-linear fit of at least TREND_R2."""
    if len(eps) < MIN_YEARS:
        return EpsTrend(False, None, None, "there are too few years of EPS to see a trend")
    if any(v <= 0 for v in eps.values()):
        years = ", ".join(k for k, v in eps.items() if v <= 0)
        return EpsTrend(False, None, None, f"EPS was zero or negative in {years}")
    fit = loglinear(eps)
    if fit is None:
        return EpsTrend(False, None, None, "EPS cannot be fitted to a trend")
    if fit.r2 < TREND_R2:
        return EpsTrend(False, fit.r2, fit.growth, f"EPS does not follow a steady trend (the fit explains only {fit.r2:.0%} of its movement)")
    return EpsTrend(True, fit.r2, fit.growth, f"EPS follows a steady trend of {fit.growth:.1%} a year (fit {fit.r2:.0%})")


@dataclass
class EpsGrowthReview:
    endpoint: float | None                      # first-year to last-year growth, as the template computes it
    robust: float | None                        # the log-linear growth of the years that are not extraordinary
    extraordinary: list[str] = field(default_factory=list)
    r2: float | None = None
    skewed: bool = False
    values: dict[str, float] = field(default_factory=dict)


def extraordinary_eps_years(eps: dict[str, float]) -> list[str]:
    """Years whose EPS is far from the log-linear trend of the whole history (an extraordinary gain, loss or dip)."""
    if len(eps) < MIN_YEARS:
        return []
    bad = [k for k, v in eps.items() if v <= 0]
    positive = {k: v for k, v in eps.items() if v > 0}
    if len(positive) < MIN_YEARS:
        return bad
    fit = loglinear(eps, exclude=bad)
    if fit is None:
        return bad
    # residuals from the fitted line
    keys = list(eps)
    xs = {k: i for i, k in enumerate(keys)}
    pts = [(xs[k], math.log(v)) for k, v in positive.items()]
    mx, my = statistics.mean(x for x, _ in pts), statistics.mean(y for _, y in pts)
    slope = math.log(1.0 + fit.growth)
    intercept = my - slope * mx
    resid = {k: math.log(v) - (intercept + slope * xs[k]) for k, v in positive.items()}
    scale = _mad(list(resid.values()))
    out = [k for k, r in resid.items() if abs(r) > max(EXTRAORDINARY_Z * scale, EXTRAORDINARY_LOG)]
    if len(out) > MAX_OFF_SHARE * len(eps):
        return bad            # too many unusual years: the whole history is irregular, nothing to trim
    return bad + [k for k in out if k not in bad]


def review_eps_growth(eps: dict[str, float], endpoint: float | None) -> EpsGrowthReview:
    """Is the endpoint growth rate skewed by extraordinary years? When it is, `robust` is the rate of the other years."""
    result = EpsGrowthReview(endpoint, None, values=dict(eps))
    if len(eps) < MIN_YEARS:
        return result
    extra = extraordinary_eps_years(eps)
    result.extraordinary = extra
    kept = {k: v for k, v in eps.items() if k not in extra and v > 0}
    if len(kept) < MIN_YEARS:
        return result
    fit = loglinear(eps, exclude=extra)
    if fit is None:
        return result
    result.robust, result.r2 = fit.growth, fit.r2
    result.skewed = bool(extra) and endpoint is not None and abs(endpoint - fit.growth) >= SKEW_MATERIAL
    return result
