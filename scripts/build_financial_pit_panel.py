#!/usr/bin/env python3
"""Build an announcement-date-aware 49-company valuation/financial panel.

Financial values are visible only on/after their announcement dates. Historical
vendor valuation rows retain their source date but are not claimed to be vintage-
verified. Public CSV export is blocked until an explicit redistribution licence
is recorded through PUBLIC_DATA_REPUBLISH_LICENSE_APPROVED=YES.
"""
from __future__ import annotations
import csv, json, os, math
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIN_PATH = ROOT / "data/financial-standardized/company-financials-2021-2025.json"
VAL_PATH = ROOT / "data/valuation-history/generated/valuation-monthly.csv"
REPORT_PATH = ROOT / "data/valuation-model/issuer-report-index-49.json"
OUT_DIR = ROOT / "data/financial-standardized"
AUDIT_PATH = OUT_DIR / "pit-panel-coverage-audit.json"
PANEL_PATH = OUT_DIR / "company-valuation-financial-pit.csv"

METRICS = {
    "revenue": ("income", "revenue"), "net_profit_parent": ("income", "netProfitParent"),
    "net_profit": ("income", "netProfit"), "operating_profit": ("income", "operatingProfit"),
    "profit_before_tax": ("income", "profitBeforeTax"), "income_tax": ("income", "incomeTax"),
    "basic_eps": ("income", "basicEps"), "diluted_eps": ("income", "dilutedEps"),
    "total_assets": ("balance", "totalAssets"), "total_liabilities": ("balance", "totalLiabilities"),
    "current_liabilities": ("balance", "currentLiabilities"), "parent_equity": ("balance", "parentEquity"),
    "cash_and_cash_equivalents": ("balance", "cashAndCashEquivalents"),
    "restricted_cash": ("balance", "restrictedCash"), "short_borrowings": ("balance", "shortBorrowings"),
    "long_borrowings": ("balance", "longBorrowings"), "bonds_payable": ("balance", "bondsPayable"),
    "lease_liabilities": ("balance", "leaseLiabilities"), "goodwill": ("balance", "goodwill"),
    "operating_cash_flow": ("cashflow", "operatingCashFlow"), "capex": ("cashflow", "capex"),
    "dividends_paid_only": ("cashflow", "dividendsPaidOnly"),
    "acquisitions_paid": ("cashflow", "acquisitionsPaid"),
    "investments_purchased": ("cashflow", "investmentsPurchased"),
    "debt_repayments": ("cashflow", "debtRepayments"),
}
VAL_FIELDS = ["close", "peTtm", "pb", "psTtm", "peTtmPct5Y", "peTtmPct10Y",
              "pbPct5Y", "pbPct10Y", "psTtmPct5Y", "psTtmPct10Y"]


def iso_date(value):
    if value in (None, "", "null"):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError:
        return None


def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def field_record(annual, section, key):
    return (((annual or {}).get(section) or {}).get("fields") or {}).get(key) or {}


def official_report_map():
    if not REPORT_PATH.exists():
        return {}
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    return {r.get("code"): r for r in payload.get("records", []) if r.get("code")}


def collect_financial_observations(companies, report_map):
    by_company = defaultdict(lambda: defaultdict(list))
    audit = {}
    for company in companies:
        code = company.get("primaryListingCode") or str(company.get("code", "")).split("/")[0].strip()
        cstats = {"annualRows": 0, "annualMetricValues": 0, "annualMetricWithAnnouncementDate": 0,
                  "annualMetricMissingAnnouncementDate": 0, "annualMetricsWithOfficialReportDate": 0,
                  "annualMetricsWithProviderAnnouncementDate": 0, "ttmFields": 0,
                  "ttmFieldsWithKnownAt": 0, "financialSourceStatusPending": 0}
        report = report_map.get(code, {})
        for annual in company.get("annual", []):
            cstats["annualRows"] += 1
            period_year = annual.get("year")
            for metric, (section, field_name) in METRICS.items():
                item = annual.get(section) or {}
                rec = field_record(annual, section, field_name)
                value = finite_number(rec.get("value"))
                if value is None:
                    continue
                cstats["annualMetricValues"] += 1
                known_at = iso_date(item.get("announcementDate"))
                official = (report.get("annualReports") or {}).get(str(period_year)) or (report.get("annual2025") if period_year == 2025 else None)
                if official and iso_date(official.get("announcementDate")):
                    known_at = iso_date(official.get("announcementDate"))
                    cstats["annualMetricsWithOfficialReportDate"] += 1
                elif known_at:
                    cstats["annualMetricsWithProviderAnnouncementDate"] += 1
                if known_at:
                    cstats["annualMetricWithAnnouncementDate"] += 1
                else:
                    cstats["annualMetricMissingAnnouncementDate"] += 1
                if rec.get("sourceVerification") != "verified":
                    cstats["financialSourceStatusPending"] += 1
                by_company[code][metric].append({
                    "value": value, "report_period": iso_date(item.get("reportDate")),
                    "fiscal_year": period_year, "available_at": known_at,
                    "announcement_date_source": "official_issuer_report_index" if official and known_at == iso_date(official.get("announcementDate")) else "provider_announcement_field",
                    "currency": item.get("currency"), "reported_unit": item.get("reportedUnit"),
                    "source_provider": item.get("provider"), "source_url": item.get("sourceUrl"),
                    "source_field": rec.get("sourceField"), "raw_value": rec.get("rawValue"),
                    "mapping_status": rec.get("mappingStatus"),
                    "source_verification": rec.get("sourceVerification"),
                    "official_document_url": (official or {}).get("pdfUrl"),
                })
        ttm = company.get("ttm") or {}
        for key, rec in (ttm.get("fields") or {}).items():
            value = finite_number(rec.get("value"))
            if value is None:
                continue
            cstats["ttmFields"] += 1
            known_at = iso_date(ttm.get("knownAt"))
            if known_at:
                cstats["ttmFieldsWithKnownAt"] += 1
            metric = "ttm_" + key
            by_company[code][metric].append({
                "value": value, "report_period": ttm.get("asOf"), "fiscal_year": "TTM",
                "available_at": known_at,
                "announcement_date_source": "max_of_ttm_source_announcements" if known_at else "missing_source_announcement_dates",
                "currency": company.get("marketCurrency"), "reported_unit": None,
                "source_provider": "derived_from_standardized_financial_statements", "source_url": None,
                "source_field": key, "raw_value": None, "mapping_status": "formula_derived",
                "source_verification": "pending_official_report_crosscheck",
                "official_document_url": None, "formula": rec.get("formula"), "inputs": rec.get("inputs"),
            })
        for metric in list(by_company[code]):
            by_company[code][metric].sort(key=lambda x: (
                x.get("available_at") or "0000-00-00", x.get("report_period") or ""))
        audit[code] = cstats
    return by_company, audit


def latest_available(observations, as_of):
    eligible = [x for x in observations if x.get("available_at") and x["available_at"] <= as_of]
    return eligible[-1] if eligible else None


def main():
    if not FIN_PATH.exists() or not VAL_PATH.exists():
        raise SystemExit("Missing standardized financial JSON or valuation-monthly.csv")
    fin = json.loads(FIN_PATH.read_text(encoding="utf-8"))
    report_map = official_report_map()
    observations, company_audit = collect_financial_observations(fin.get("companies", []), report_map)
    valuation_rows = []
    with VAL_PATH.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code, as_of = (row.get("code") or "").strip().upper(), iso_date(row.get("date"))
            if code and as_of:
                valuation_rows.append((code, as_of, row))
    valuation_rows.sort(key=lambda x: (x[0], x[1]))

    per_company = defaultdict(lambda: {"valuationRows": 0, "rowsWithAnyPointInTimeFinancials": 0,
                                       "rowsWithSixCoreMetricsAvailable": 0, "lastValuationDate": None})
    export_allowed = os.getenv("PUBLIC_DATA_REPUBLISH_LICENSE_APPROVED", "").strip().upper() == "YES"
    written = 0
    missing_ann = sum(x["annualMetricMissingAnnouncementDate"] for x in company_audit.values())
    total_ann_values = sum(x["annualMetricValues"] for x in company_audit.values())
    headers = ["code", "issuerName", "valuation_observation_date", "valuation_source",
               "valuation_source_url", "valuation_currency", "valuation_pit_vintage_status"]
    headers += ["valuation_" + x for x in VAL_FIELDS]
    metric_names = sorted({m for code_map in observations.values() for m in code_map})
    for metric in metric_names:
        headers += [metric + suffix for suffix in (
            "_value", "_report_period", "_available_at", "_announcement_date_source", "_currency",
            "_reported_unit", "_source_provider", "_source_url", "_source_field",
            "_source_verification", "_official_document_url")]
    writer = None
    out = None
    if export_allowed:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = PANEL_PATH.open("w", encoding="utf-8-sig", newline="")
        writer = csv.DictWriter(out, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
    try:
        for code, as_of, val in valuation_rows:
            stats = per_company[code]
            stats["valuationRows"] += 1
            stats["lastValuationDate"] = as_of
            row = {"code": code, "issuerName": val.get("issuerName"),
                   "valuation_observation_date": as_of, "valuation_source": val.get("source"),
                   "valuation_source_url": val.get("sourceUrl"), "valuation_currency": val.get("currency"),
                   "valuation_pit_vintage_status": "historical_vendor_observation; source_calculation_vintage_not_independently_verified"}
            for field in VAL_FIELDS:
                row["valuation_" + field] = val.get(field)
            used, all_core_dated = 0, True
            for metric in metric_names:
                item = latest_available(observations.get(code, {}).get(metric, []), as_of)
                if item:
                    used += 1
                    for key in ("value", "report_period", "available_at", "announcement_date_source",
                                "currency", "reported_unit", "source_provider", "source_url",
                                "source_field", "source_verification", "official_document_url"):
                        row[metric + "_" + key] = item.get(key)
                if metric in {"revenue", "net_profit_parent", "total_assets", "parent_equity",
                              "operating_cash_flow", "capex"} and item is None:
                    all_core_dated = False
            if used:
                stats["rowsWithAnyPointInTimeFinancials"] += 1
            if all_core_dated:
                stats["rowsWithSixCoreMetricsAvailable"] += 1
            if writer:
                writer.writerow(row)
                written += 1
    finally:
        if out:
            out.close()

    audit = {
        "schemaVersion": "1.0.0",
        "generatedFrom": {"financialFile": str(FIN_PATH.relative_to(ROOT)),
                          "valuationFile": str(VAL_PATH.relative_to(ROOT)),
                          "officialReportIndex": str(REPORT_PATH.relative_to(ROOT)),
                          "financialSourceArchiveSha256": fin.get("sourceArchiveSha256")},
        "companyCount": len(fin.get("companies", [])),
        "valuationMonthlyObservations": len(valuation_rows),
        "annualFinancialMetricValues": total_ann_values,
        "annualFinancialValuesWithAnnouncementDate": total_ann_values - missing_ann,
        "annualFinancialValuesMissingAnnouncementDate": missing_ann,
        "companiesWithAtLeastOneOfficialAnnualReportLink2021To2025": sum(any(bool(v) for v in (r.get("annualReports") or {}).values()) or bool((r.get("annual2025") or {}).get("pdfUrl")) for r in report_map.values()),
        "companiesWithAnyPointInTimePanelRows": sum(v["rowsWithAnyPointInTimeFinancials"] > 0 for v in per_company.values()),
        "companiesWithNoPointInTimePanelRows": sum(v["valuationRows"] > 0 and v["rowsWithAnyPointInTimeFinancials"] == 0 for v in per_company.values()),
        "financialPointInTimeRule": "Only values with a parsed announcement date <= valuation observation date are eligible. Reporting period end is never used as availability date.",
        "valuationVintageLimitation": "Valuation observation dates are retained, but vendor backfill/revision vintage has not been independently proved; do not interpret as a complete historically-known valuation snapshot.",
        "financialVerificationLimitation": "Provider-mapped values remain pending until reconciled to official issuer/exchange report pages and notes. A report link alone is not item-level verification.",
        "unitCurrencyRule": "Values remain in issuer-reported unit and currency; cross-company arithmetic is blocked where currency/unit is not explicit.",
        "publicPanelExport": "written" if export_allowed else "blocked_pending_explicit_redistribution_license_approval",
        "publicPanelPath": str(PANEL_PATH.relative_to(ROOT)) if export_allowed else None,
        "exportedRows": written,
        "perCompany": {code: {**stats, "financialMetricAudit": company_audit.get(code, {})}
                       for code, stats in sorted(per_company.items())},
        "companyFinancialAnnouncementAudit": company_audit,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in audit.items()
                      if k not in ("perCompany", "companyFinancialAnnouncementAudit")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
