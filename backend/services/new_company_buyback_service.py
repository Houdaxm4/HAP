"""Ten-year share-repurchase dollars and shares, with derivation and analysis."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.new_company import (
    BuybackAbsenceClass,
    BuybackAnalysis,
    BuybackYearResult,
    NewCompanyBuybackReport,
)
from services.annual_period_service import detect_year_columns
from services.sec_service import SecService, SecServiceError

_DOLLAR_TAGS = (
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsForRepurchaseOfEquity",
    "TreasuryStockValueAcquiredCostMethod",
    "StockRepurchasedDuringPeriodValue",
)
_SHARE_TAGS = (
    "StockRepurchasedDuringPeriodShares",
    "TreasuryStockSharesAcquired",
    "CommonStockSharesRepurchased",
)
_PERIOD_VALUE_TAGS = ("StockRepurchasedDuringPeriodValue",)
_AVG_PRICE_TAGS = (
    "TreasuryStockAcquiredAverageCostPerShare",
    "StockRepurchasedDuringPeriodAverageCostPerShare",
)
_BEGIN_SHARES = ("CommonStockSharesOutstanding",)
_WAS_DILUTED = ("WeightedAverageNumberOfDilutedSharesOutstanding",)
_SBC_TAGS = ("AllocatedShareBasedCompensationExpense", "ShareBasedCompensation")
_FCF_PROXY = ("NetCashProvidedByUsedInOperatingActivities",)
_CAPEX = ("PaymentsToAcquirePropertyPlantAndEquipment",)

_MIN_IMPLIED_PRICE = 5.0
_MAX_IMPLIED_PRICE = 5_000.0
_VALUE_RECONCILE_TOL = 0.25

_TABLE_WINDOW = re.compile(
    r"total number of shares repurchased.{0,1500}?#\s*of\s*Shares.{0,240}?Value(?P<body>.{0,6000}?)(?:Total|Impact of|Comparability|Dividends Cash|Intellectual|Restructuring)",
    re.IGNORECASE | re.DOTALL,
)
_YEAR_ROW = re.compile(
    r"(?P<year>20\d{2})\s+(?P<shares>[\d,]+)\s+\$?\s*(?P<value>[\d,]+)"
)
_NO_SHARES_RE = re.compile(
    r"there were no shares repurchased during the (?:twelve|12) months ended[^\n.]{0,160}",
    re.IGNORECASE,
)
_CFS_REPO_LINE = re.compile(
    r"repurchase of common (?:shares|stock)(?P<rest>[^\n]{0,240})",
    re.IGNORECASE,
)
_CFS_TOKEN = re.compile(r"—|--|–|-|\([^)]+\)|\$?[\d,]+(?:\.\d+)?")
_CFS_ZERO_TOKEN = re.compile(r"^(?:—|--|–|-|\$?0(?:\.0+)?)$")


def _scale(val: float, *, shares: bool = False) -> float:
    if shares:
        return val / 1_000_000.0 if abs(val) >= 10_000 else val
    return val / 1_000_000.0 if abs(val) >= 10_000 else val


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


_MATERIAL_BUYBACK = 0.05


def _fy_token(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return f"FY{digits}" if digits else None


def _is_share_label(label: str) -> bool:
    return any(
        token in label
        for token in (
            "shares repurchased",
            "share repurchased",
            "shares buyback",
            "buyback shares",
            "number of shares repurchased",
        )
    )


def _is_dollar_label(label: str) -> bool:
    if _is_share_label(label):
        return False
    return any(
        token in label
        for token in (
            "amount paid",
            "paid for shares",
            "$ paid",
            "buybacks",
            "share repurchases",
            "repurchase of common stock",
            "payments for repurchase",
            "dollars spent",
        )
    )


def _prefer_template_rows(ws, shares: int | None, dollars: int | None) -> tuple[int | None, int | None]:
    """Use rows 87–88 only when their labels are the share and dollar fields."""
    label_87 = str(ws.cell(87, 1).value or "").strip().lower()
    label_88 = str(ws.cell(88, 1).value or "").strip().lower()
    if _is_share_label(label_87):
        shares = 87
    if _is_dollar_label(label_88):
        dollars = 88
    return shares, dollars


def _fy_int(token: str) -> int:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    return int(digits) if digits else 0


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|tr|div|h[1-6]|li|table)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&#8217;|&rsquo;", "'", text)
    text = re.sub(r"&#8212;|&mdash;|&ndash;", "-", text)
    text = re.sub(r"&#32;|&nbsp;|&#160;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text


def parse_share_repurchase_program_table(text: str) -> dict[int, dict[str, Any]]:
    """Parse the 10-K capital-return table (values in thousands).

    Returns fiscal year → {shares_millions, dollars_millions}.
    """
    match = _TABLE_WINDOW.search(text)
    if not match:
        return {}
    body = match.group("body")
    out: dict[int, dict[str, Any]] = {}
    for row in _YEAR_ROW.finditer(body):
        year = int(row.group("year"))
        shares_thousands = float(row.group("shares").replace(",", ""))
        value_thousands = float(row.group("value").replace(",", ""))
        out[year] = {
            "shares": shares_thousands / 1_000.0,
            "dollars": value_thousands / 1_000.0,
            "units": "table_in_thousands → millions",
        }
    return out


def parse_no_shares_repurchased_narrative(text: str) -> dict[int, dict[str, Any]]:
    """Parse explicit 10-K statements that no shares were repurchased.

    Returns fiscal year → {shares: 0, dollars: 0}. Does not infer zeros from
    omitted tables, share-count changes, or treasury-stock balances.
    """
    out: dict[int, dict[str, Any]] = {}
    for match in _NO_SHARES_RE.finditer(text):
        for year in (int(y) for y in re.findall(r"20\d{2}", match.group(0))):
            out[year] = {
                "shares": 0.0,
                "dollars": 0.0,
                "units": "explicit_zero",
                "source_kind": "10k_no_shares_repurchased_narrative",
            }
    return out


def parse_cfs_repurchase_dash_zeros(text: str, filing_year: int) -> dict[int, dict[str, Any]]:
    """Record CFS repurchase-line dashes as explicit zeros for the filing year.

    Non-dash amounts are ignored: cash-flow statement units (thousands vs
    millions) are not assumed. Only an em-dash, hyphen, or literal zero in the
    current/comparative columns is treated as a disclosed $0 outflow.
    """
    if not filing_year:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for match in _CFS_REPO_LINE.finditer(text):
        tokens = _CFS_TOKEN.findall(match.group("rest") or "")
        for i, tok in enumerate(tokens[:3]):
            cleaned = tok.strip()
            if not _CFS_ZERO_TOKEN.match(cleaned):
                continue
            year = int(filing_year) - i
            out[year] = {
                "shares": 0.0,
                "dollars": 0.0,
                "units": "cfs_dash_or_zero",
                "source_kind": "10k_cfs_repurchase_dash_zero",
            }
    return out


def _iter_tag_entries(company_facts: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    facts = company_facts.get("facts") or {}
    for taxonomy in ("us-gaap", "dei", "ifrs-full"):
        payload = (facts.get(taxonomy) or {}).get(tag)
        if not payload:
            continue
        units = payload.get("units") or {}
        rows: list[dict[str, Any]] = []
        for unit, entries in units.items():
            for entry in entries or []:
                row = dict(entry)
                row["_unit"] = unit
                row["_tag"] = tag
                rows.append(row)
        return rows
    return []


def _economic_year(entry: dict[str, Any]) -> int | None:
    frame = entry.get("frame")
    if isinstance(frame, str):
        annual = re.fullmatch(r"CY(\d{4})", frame.strip())
        if annual:
            return int(annual.group(1))
    end = entry.get("end")
    if isinstance(end, str) and re.match(r"^(19|20)\d{2}", end):
        return int(end[:4])
    fy = entry.get("fy")
    return int(fy) if fy else None


def _is_annual_duration(entry: dict[str, Any], target_year: int) -> bool:
    """Reject multi-year cumulative program-to-date facts."""
    start_d = _parse_date(entry.get("start"))
    end_d = _parse_date(entry.get("end"))
    if start_d and end_d:
        days = (end_d - start_d).days
        if days > 400 or days < 300:
            return False
        return True
    frame = entry.get("frame")
    if frame == f"CY{target_year}" and entry.get("fp") == "FY":
        return True
    if entry.get("fp") == "FY" and entry.get("form") in {"10-K", "10-K/A"} and start_d is None:
        return _economic_year(entry) == target_year
    return False


class NewCompanyBuybackService:
    DOLLARS_DEFINITION = (
        "gross_common_stock_repurchase_cash_outflow excluding employee tax-withholding "
        "when separately disclosed; includes excise tax only when the filing includes it "
        "in repurchase cost."
    )

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        company_facts: dict[str, Any] | None = None,
        market_cap: float | None = None,
        intrinsic_value: float | None = None,
        sec_manifest: dict[str, Any] | None = None,
        cache_dir: Path | None = None,
        filings_text: dict[str, str] | None = None,
        write_policy: str = "new_company",
        new_fiscal_year: str | None = None,
    ) -> NewCompanyBuybackReport:
        sec = SecService(cache_dir=cache_dir)
        years: list[BuybackYearResult] = []
        warnings: list[str] = []
        sbc_total = 0.0
        fcf_total = 0.0
        dollars_total = 0.0
        narrative = self._narrative_disclosures(
            sec,
            sec_manifest=sec_manifest,
            filings_text=filings_text,
            warnings=warnings,
        )

        for fy in fiscal_years:
            year_n = _fy_int(fy)
            dollars, d_src = self._annual_dollar_fact(company_facts, fy)
            shares, s_src = self._annual_share_fact(company_facts, fy)
            avg, a_src = self._fact(sec, company_facts, fy, _AVG_PRICE_TAGS, scale=False)
            begin, _ = self._fact(sec, company_facts, fy, _BEGIN_SHARES, scale=True, shares=True)
            was, _ = self._fact(sec, company_facts, fy, _WAS_DILUTED, scale=True, shares=True)
            end_shares, _ = self._fact(
                sec,
                company_facts,
                fy,
                ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"),
                scale=True,
                shares=True,
            )
            issued, _ = self._fact(
                sec, company_facts, fy, ("StockIssuedDuringPeriodSharesNewIssues", "CommonStockSharesIssued"), scale=True, shares=True
            )
            withholding, _ = self._fact(
                sec,
                company_facts,
                fy,
                ("PaymentsRelatedToTaxWithholdingForShareBasedCompensation",),
                scale=True,
            )
            sbc_shares, _ = self._fact(
                sec, company_facts, fy, ("ShareBasedCompensationArrangementByShareBasedPaymentAwardShares",), scale=True, shares=True
            )
            acquisition, _ = self._fact(
                sec, company_facts, fy, ("StockIssuedDuringPeriodSharesAcquisitions",), scale=True, shares=True
            )
            sbc, _ = self._fact(sec, company_facts, fy, _SBC_TAGS, scale=True)
            cfo, _ = self._fact(sec, company_facts, fy, _FCF_PROXY, scale=True)
            capex, _ = self._fact(sec, company_facts, fy, _CAPEX, scale=True)
            derived = False
            formula = None
            year_warnings: list[str] = []
            avg_derived = False

            if shares is not None and dollars is not None and not self._implied_price_ok(dollars, shares):
                year_warnings.append("BUYBACK_XBRL_SHARES_REJECTED_IMPLAUSIBLE_PRICE")
                shares, s_src = None, None
            if shares is not None and dollars is not None and not self._period_value_reconciles(
                company_facts, fy, dollars
            ):
                year_warnings.append("BUYBACK_XBRL_SHARES_REJECTED_CUMULATIVE_OR_UNRECONCILED")
                shares, s_src = None, None

            disclosed = narrative.get(year_n)
            if disclosed:
                kind = disclosed.get("source_kind") or ""
                src = disclosed.get("source") or "sec_10k:share_repurchase_disclosure"
                if disclosed.get("shares") is not None:
                    shares = float(disclosed["shares"])
                    s_src = src
                if dollars is None and disclosed.get("dollars") is not None:
                    dollars = float(disclosed["dollars"])
                    d_src = src
                elif (
                    dollars is not None
                    and disclosed.get("dollars") is not None
                    and kind == "share_repurchase_program_table"
                    and abs(dollars - float(disclosed["dollars"])) > max(0.05 * abs(dollars), 0.05)
                ):
                    year_warnings.append("BUYBACK_10K_TABLE_DOLLARS_DIVERGE_FROM_CASH_FLOW")

            if shares is None and dollars is not None and avg not in (None, 0):
                shares = dollars / avg
                derived = True
                formula = "repurchase_dollars / disclosed_average_repurchase_price"
                s_src = f"derived:{a_src}"
            elif avg is None and dollars and shares not in (None, 0):
                avg = dollars / shares
                avg_derived = True
                year_warnings.append("BUYBACK_AVERAGE_PRICE_DERIVED")
            absence = None
            if dollars is None and shares is None:
                absence = BuybackAbsenceClass.NOT_DISCLOSED
                warnings.append(f"BUYBACK_DOLLARS_COVERAGE_INCOMPLETE: {fy}")
                warnings.append(f"BUYBACK_SHARES_COVERAGE_INCOMPLETE: {fy}")
                year_warnings.append(
                    "Attempted SEC company facts "
                    "(PaymentsForRepurchaseOfCommonStock, PaymentsForRepurchaseOfEquity, "
                    "TreasuryStockValueAcquiredCostMethod, StockRepurchasedDuringPeriodValue, "
                    "StockRepurchasedDuringPeriodShares, TreasuryStockSharesAcquired) "
                    "and the 10-K repurchase table, explicit no-repurchase narrative, "
                    "and cash-flow dash. No annual repurchase fact was found. "
                    "A blank or workbook zero was not treated as a reported zero."
                )
            elif dollars == 0 and (shares is None or shares == 0):
                absence = BuybackAbsenceClass.REPORTED_ZERO
            if dollars is None and shares is not None:
                warnings.append(f"BUYBACK_DOLLARS_COVERAGE_INCOMPLETE: {fy}")
            if shares is None and dollars is not None and not derived:
                warnings.append(f"BUYBACK_SHARES_COVERAGE_INCOMPLETE: {fy}")
            if derived:
                warnings.append(f"BUYBACK_SHARES_DERIVED: {fy}")

            if begin is not None and shares is not None and end_shares is not None:
                delta = end_shares - begin
                if abs(delta) > abs(shares or 0) * 1.5 + 1e-6:
                    year_warnings.append(
                        "Share-count change is not used as buybacks; Δshares diverges from disclosed/derived repurchases."
                    )
            if sbc:
                sbc_total += sbc
            fcf = None
            if cfo is not None:
                fcf = cfo - abs(capex or 0.0)
                fcf_total += fcf
            if dollars:
                dollars_total += dollars

            years.append(
                BuybackYearResult(
                    fiscal_year=fy,
                    dollars=dollars,
                    shares=shares,
                    average_price=avg if avg is not None else (
                        (dollars / shares) if dollars and shares else None
                    ),
                    dollars_source=d_src,
                    shares_source=s_src,
                    shares_derived=derived,
                    derivation_formula=formula,
                    dollars_definition=self.DOLLARS_DEFINITION,
                    exclusions=[
                        "employee_share_withholding_when_separately_disclosed",
                        "share_issuance_proceeds",
                        "acquisition_related_share_activity",
                        "change_in_shares_outstanding_not_used_as_buyback",
                        "treasury_share_balance_delta_not_used_as_buyback",
                        "cumulative_program_to_date_xbrl_not_used_as_annual",
                    ],
                    beginning_shares=begin,
                    issued_shares=issued,
                    ending_shares=end_shares,
                    diluted_was=was,
                    sbc_dilution_shares=sbc_shares,
                    employee_tax_withholding=withholding,
                    acquisition_related_equity=acquisition,
                    other_share_changes=None,
                    average_price_derived=avg_derived,
                    derivation_units="USD_millions / USD_per_share → million_shares" if derived else None,
                    absence_class=absence,
                    confidence=0.5 if derived else (0.85 if dollars is not None else 0.2),
                    warnings=year_warnings,
                )
            )

        first_was = next((y.diluted_was for y in years if y.diluted_was is not None), None)
        last_was = next((y.diluted_was for y in reversed(years) if y.diluted_was is not None), None)
        share_chg = None
        if first_was is not None and last_was is not None:
            share_chg = last_was - first_was
        cum_shares = sum(y.shares or 0.0 for y in years)
        sbc_offset = bool(sbc_total and dollars_total and sbc_total > 0.25 * dollars_total)
        funded = None
        pct_fcf = None
        if dollars_total:
            if fcf_total:
                pct_fcf = dollars_total / fcf_total if fcf_total else None
            if fcf_total >= dollars_total:
                funded = "free_cash_flow"
            elif fcf_total > 0:
                funded = "free_cash_flow_and_cash_balances"
            else:
                funded = "cash_balances_or_debt"
        vs_iv = None
        prices = [y.average_price for y in years if y.average_price]
        if intrinsic_value and prices:
            avg_px = sum(prices) / len(prices)
            vs_iv = "created_per_share_value" if avg_px < intrinsic_value else "likely_destroyed_per_share_value"
        analysis = BuybackAnalysis(
            cumulative_dollars=dollars_total or None,
            cumulative_shares=cum_shares or None,
            diluted_share_count_change=share_chg,
            sbc_offset_material=sbc_offset,
            funded_by=funded,
            buybacks_pct_of_fcf=pct_fcf,
            value_created_or_destroyed=vs_iv,
            notes=[
                "Large repurchase dollars are not by themselves shareholder-friendly.",
                "Change in shares outstanding is not used as the buyback measure.",
                "Treasury-share balance changes are not used as the buyback measure.",
            ]
            + (["Stock-based compensation materially offset share reduction."] if sbc_offset else []),
        )
        cells_written, discrepancies = self._write_buyback_schedule(
            workbook_path,
            years,
            write_policy=write_policy,
            new_fiscal_year=new_fiscal_year,
        )
        complete = all(
            y.absence_class in {BuybackAbsenceClass.REPORTED_ZERO, BuybackAbsenceClass.NOT_APPLICABLE}
            or (y.dollars is not None and (y.shares is not None or y.shares_derived))
            or y.absence_class == BuybackAbsenceClass.NOT_DISCLOSED
            for y in years
        )
        return NewCompanyBuybackReport(
            analysis_id=analysis_id,
            ticker=ticker,
            years=years,
            analysis=analysis,
            complete=complete,
            warnings=warnings,
            write_policy=write_policy,
            cells_written=cells_written,
            discrepancies=discrepancies,
            summary=(
                f"Buybacks: cumulative_dollars={dollars_total}; cumulative_shares={cum_shares}; "
                f"sbc_offset={sbc_offset}; funded_by={funded}; policy={write_policy}."
            ),
        )

    @staticmethod
    def _implied_price_ok(dollars_m: float, shares_m: float) -> bool:
        if shares_m in (None, 0) or dollars_m is None:
            return True
        price = (dollars_m * 1_000_000.0) / (shares_m * 1_000_000.0)
        return _MIN_IMPLIED_PRICE <= price <= _MAX_IMPLIED_PRICE

    @staticmethod
    def _period_value_reconciles(
        company_facts: dict[str, Any] | None, fy: str, dollars_m: float
    ) -> bool:
        if not company_facts or dollars_m is None:
            return True
        year_n = _fy_int(fy)
        for tag in _PERIOD_VALUE_TAGS:
            for entry in _iter_tag_entries(company_facts, tag):
                if _economic_year(entry) != year_n:
                    continue
                if not _is_annual_duration(entry, year_n):
                    continue
                if entry.get("val") is None:
                    continue
                val = _scale(float(entry["val"]))
                denom = max(abs(dollars_m), 1e-6)
                if abs(val - dollars_m) / denom > _VALUE_RECONCILE_TOL:
                    return False
        return True

    @staticmethod
    def _annual_share_fact(
        company_facts: dict[str, Any] | None, fy: str
    ) -> tuple[float | None, str | None]:
        if not company_facts:
            return None, None
        year_n = _fy_int(fy)
        for tag in _SHARE_TAGS:
            for entry in _iter_tag_entries(company_facts, tag):
                if entry.get("val") is None:
                    continue
                if _economic_year(entry) != year_n:
                    continue
                if not _is_annual_duration(entry, year_n):
                    continue
                val = _scale(float(entry["val"]), shares=True)
                return val, f"sec_xbrl:{tag}"
        return None, None

    @staticmethod
    def _annual_dollar_fact(
        company_facts: dict[str, Any] | None, fy: str
    ) -> tuple[float | None, str | None]:
        if not company_facts:
            return None, None
        year_n = _fy_int(fy)
        for tag in _DOLLAR_TAGS:
            for entry in _iter_tag_entries(company_facts, tag):
                if entry.get("val") is None:
                    continue
                if _economic_year(entry) != year_n:
                    continue
                if not _is_annual_duration(entry, year_n):
                    continue
                val = _scale(float(entry["val"]))
                return val, f"sec_xbrl:{tag}"
        return None, None

    def _narrative_disclosures(
        self,
        sec: SecService,
        *,
        sec_manifest: dict[str, Any] | None,
        filings_text: dict[str, str] | None,
        warnings: list[str],
    ) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        texts: list[tuple[str, str, str | None]] = []
        if filings_text:
            for key, body in filings_text.items():
                texts.append((str(key), body, None))
        elif sec_manifest:
            cik = str(sec_manifest.get("cik") or "")
            for filing in sec_manifest.get("selected_filings") or []:
                if str(filing.get("filing_type") or "").upper() not in {"10-K", "10-K/A"}:
                    continue
                url = filing.get("document_url")
                fy = filing.get("fiscal_year")
                if not url or "Archives/edgar" not in str(url):
                    continue
                try:
                    html = sec.fetch_document_text(
                        url, cik=cik or None, cache_name=f"10k_buybacks_{fy}.htm"
                    )
                except (SecServiceError, OSError) as exc:
                    warnings.append(f"BUYBACK_10K_RETRIEVAL_FAILED: FY{fy}: {exc}")
                    continue
                texts.append((f"FY{fy}", html, url))
        for label, body, url in texts:
            plain = html_to_text(body)
            filing_year = _fy_int(label)
            parsed = parse_share_repurchase_program_table(plain)
            source = f"sec_10k:share_repurchase_program_table:{label}"
            if url:
                source = f"{source}:{url}"
            for year, payload in parsed.items():
                if year in out:
                    continue
                row = dict(payload)
                row["source"] = source
                row["source_kind"] = "share_repurchase_program_table"
                out[year] = row
            narrative_zeros = parse_no_shares_repurchased_narrative(plain)
            n_src = f"sec_10k:no_shares_repurchased_narrative:{label}"
            if url:
                n_src = f"{n_src}:{url}"
            for year, payload in narrative_zeros.items():
                if year in out:
                    continue
                row = dict(payload)
                row["source"] = n_src
                out[year] = row
            cfs_zeros = parse_cfs_repurchase_dash_zeros(plain, filing_year)
            c_src = f"sec_10k:cfs_repurchase_dash_zero:{label}"
            if url:
                c_src = f"{c_src}:{url}"
            for year, payload in cfs_zeros.items():
                if year in out:
                    continue
                row = dict(payload)
                row["source"] = c_src
                out[year] = row
        return out

    @staticmethod
    def _fact(
        sec: SecService,
        company_facts: dict[str, Any] | None,
        fy: str,
        tags: tuple[str, ...],
        *,
        scale: bool,
        shares: bool = False,
    ) -> tuple[float | None, str | None]:
        if not company_facts:
            return None, None
        for tag in tags:
            fact = sec.find_fact(company_facts, tag, fy, xbrl_tag_hint=tag)
            if fact is None or fact.value is None:
                continue
            val = float(fact.value)
            if scale:
                val = _scale(val, shares=shares)
            return val, f"sec_xbrl:{tag}"
        return None, None

    def _write_buyback_schedule(
        self,
        path: Path,
        years: list[BuybackYearResult],
        *,
        write_policy: str,
        new_fiscal_year: str | None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        written: list[str] = []
        discrepancies: list[dict[str, Any]] = []
        new_token = _fy_token(new_fiscal_year) if new_fiscal_year else None
        wb = load_workbook(path, data_only=False)
        try:
            targets = self._schedule_targets(wb)
            notes_sheet = None
            for sheet_name, d_row, s_row in targets:
                ws = wb[sheet_name]
                cols = detect_year_columns(ws, wb)
                if d_row or s_row:
                    notes_sheet = notes_sheet or sheet_name
                for year in years:
                    col = cols.get(year.fiscal_year)
                    if not col:
                        continue
                    annual_new_year = write_policy == "annual_update" and (
                        new_token is None or year.fiscal_year == new_token
                    )
                    historical = write_policy == "annual_update" and year.fiscal_year != new_token
                    allow_fill = write_policy != "annual_update" or annual_new_year
                    correct_material = write_policy != "annual_update"
                    if d_row:
                        year.dollars_cell = f"{sheet_name}!{ws.cell(d_row, col).coordinate}"
                        current = ws.cell(d_row, col).value
                        if isinstance(current, (int, float)) and not isinstance(current, bool):
                            year.workbook_dollars = float(current)
                    if s_row:
                        year.shares_cell = f"{sheet_name}!{ws.cell(s_row, col).coordinate}"
                        current = ws.cell(s_row, col).value
                        if isinstance(current, (int, float)) and not isinstance(current, bool):
                            year.workbook_shares = float(current)
                    if year.dollars is None and year.shares is None:
                        year.write_action = "not_written_evidence_missing"
                        continue
                    if d_row and year.dollars is not None:
                        action = self._write_metric(
                            ws,
                            d_row,
                            col,
                            year.dollars,
                            metric="dollars",
                            year=year,
                            allow_fill=allow_fill,
                            historical=historical,
                            correct_material=correct_material,
                            written=written,
                            discrepancies=discrepancies,
                        )
                        year.dollars_cell = f"{sheet_name}!{ws.cell(d_row, col).coordinate}"
                        year.write_action = action
                    if s_row and year.shares is not None:
                        action = self._write_metric(
                            ws,
                            s_row,
                            col,
                            year.shares,
                            metric="shares",
                            year=year,
                            allow_fill=allow_fill,
                            historical=historical,
                            correct_material=correct_material,
                            written=written,
                            discrepancies=discrepancies,
                        )
                        year.shares_cell = f"{sheet_name}!{ws.cell(s_row, col).coordinate}"
                        year.write_action = action
            if notes_sheet:
                self._write_buyback_notes(wb[notes_sheet], years, write_policy)
            wb.save(path)
        finally:
            wb.close()
        return written, discrepancies

    @staticmethod
    def _schedule_targets(wb) -> list[tuple[str, int | None, int | None]]:
        """Locate dollar and share rows. Prefer verified Income Statement rows 87–88."""
        preferred = ("Income Statement", "Income - GAAP", "Inputs")
        found: list[tuple[str, int | None, int | None]] = []
        names = [name for name in preferred if name in wb.sheetnames]
        names.extend(name for name in wb.sheetnames if name not in names and "income" in name.lower())
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            ws = wb[name]
            dollars = shares = None
            limit = min(ws.max_row or 1, 160)
            for row in range(1, limit + 1):
                label = str(ws.cell(row, 1).value or ws.cell(row, 2).value or "").strip().lower()
                if not label:
                    continue
                if _is_share_label(label) and shares is None:
                    shares = row
                elif _is_dollar_label(label) and dollars is None:
                    dollars = row
            if name == "Income Statement":
                shares, dollars = _prefer_template_rows(ws, shares, dollars)
            if dollars or shares:
                found.append((name, dollars, shares))
                if name in {"Income Statement", "Income - GAAP"}:
                    break
        return found

    def _write_metric(
        self,
        ws,
        row: int,
        col: int,
        evidence: float,
        *,
        metric: str,
        year: BuybackYearResult,
        allow_fill: bool,
        historical: bool,
        correct_material: bool,
        written: list[str],
        discrepancies: list[dict[str, Any]],
    ) -> str:
        from services.workbook_flag_service import flag_discrepancy

        cell = ws.cell(row, col)
        current = cell.value
        ref = f"{ws.title}!{cell.coordinate}"
        if isinstance(current, str) and current.startswith("="):
            return "formula_protected"
        numeric = current if isinstance(current, (int, float)) and not isinstance(current, bool) else None
        if metric == "dollars":
            year.workbook_dollars = float(numeric) if numeric is not None else None
        else:
            year.workbook_shares = float(numeric) if numeric is not None else None
        if current not in (None, ""):
            if numeric is None:
                return "preserved_non_numeric"
            relative = abs(float(numeric) - evidence) / max(abs(evidence), abs(float(numeric)), 1e-9)
            if relative <= _MATERIAL_BUYBACK:
                return "preserved"
            record = {
                "fiscal_year": year.fiscal_year,
                "metric": metric,
                "cell": ref,
                "workbook_value": float(numeric),
                "sec_value": evidence,
                "source": year.dollars_source if metric == "dollars" else year.shares_source,
                "relative_difference": round(relative, 4),
            }
            discrepancies.append(record)
            if historical or not correct_material:
                flag_discrepancy(
                    ws,
                    cell.coordinate,
                    workbook_value=numeric,
                    source_value=evidence,
                    provenance=record["source"] or "sec",
                    issue=(
                        "Buyback figure differs from SEC evidence. "
                        "Annual history was not overwritten."
                        if historical or not correct_material
                        else "Buyback figure differs from SEC evidence."
                    ),
                )
                cell.value = current
                return "discrepancy_flagged"
            cell.value = evidence
            written.append(ref)
            return "corrected_from_sec"
        if not allow_fill:
            return "historical_blank_preserved"
        if year.absence_class == BuybackAbsenceClass.NOT_DISCLOSED:
            return "missing_not_zero"
        cell.value = evidence
        written.append(ref)
        return "filled"

    @staticmethod
    def _write_buyback_notes(ws, years: list[BuybackYearResult], write_policy: str) -> None:
        from services.hap_analysis_layout_service import HapAnalysisLayoutService

        lines = []
        for year in years:
            kind = (
                "reported_zero"
                if year.absence_class == BuybackAbsenceClass.REPORTED_ZERO
                else "derived"
                if year.shares_derived
                else "explicit"
                if year.dollars is not None or year.shares is not None
                else "missing"
            )
            lines.append(
                f"{year.fiscal_year}: dollars={year.dollars} shares={year.shares} ({kind})"
            )
        HapAnalysisLayoutService().write_notes_section(
            ws,
            [
                ("Buyback definition", NewCompanyBuybackService.DOLLARS_DEFINITION),
                ("Write policy", write_policy),
                ("Source hierarchy", "SEC 10-K cash flow, repurchase table, and annual XBRL. Yahoo is not gross repurchase dollars."),
                ("Year coverage", "; ".join(lines[:12])),
                (
                    "Not used as buybacks",
                    "Share-count changes, treasury balances, program-to-date cumulative counts, and withholding.",
                ),
            ],
        )
