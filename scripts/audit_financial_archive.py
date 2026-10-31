#!/usr/bin/env python3
"""Create a transparent coverage audit for the latest raw statement archive."""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw-financials"


def main():
    archives = sorted(RAW.glob("company_statements_*.json"))
    if not archives:
        raise SystemExit("No raw company_statements archive exists; collection has not completed.")
    source = archives[-1]
    payload = json.loads(source.read_text(encoding="utf-8"))
    company_map = {}
    totals = defaultdict(int)
    for record in payload.get("records", []):
        key = (record.get("exchange"), record.get("code"))
        item = company_map.setdefault(key, {
            "exchange": record.get("exchange"),
            "code": record.get("code"),
            "company": record.get("company"),
            "provider": record.get("provider"),
            "statements": [],
        })
        rows = record.get("rows") or []
        date_fields = ("报告日", "报告日期", "STD_REPORT_DATE", "REPORT_DATE")
        dates = sorted({
            str(row.get(field))[:10]
            for row in rows for field in date_fields
            if row.get(field) not in (None, "")
        })
        item["statements"].append({
            "statement": record.get("statement"),
            "period_mode": record.get("period_mode"),
            "status": record.get("status"),
            "row_count": record.get("row_count", len(rows)),
            "date_field_candidates": [field for field in date_fields
                                      if rows and field in rows[0]],
            "unique_report_dates": len(dates),
            "first_report_date": dates[0] if dates else None,
            "last_report_date": dates[-1] if dates else None,
            "fields_sample": list(rows[0].keys()) if rows else [],
            "error": record.get("error"),
        })
        totals[record.get("status", "unknown")] += 1

    companies = list(company_map.values())
    for company in companies:
        company["statements"].sort(
            key=lambda x: (x.get("statement") or "", x.get("period_mode") or "")
        )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_archive": str(source.relative_to(ROOT)),
        "run_id": payload.get("run_id"),
        "scope": payload.get("scope"),
        "record_status_counts": dict(totals),
        "companies_with_any_rows": sum(
            any(s["row_count"] > 0 for s in c["statements"]) for c in companies
        ),
        "companies_with_all_statement_requests_retrieved": sum(
            bool(c["statements"]) and all(
                s["status"] == "retrieved" for s in c["statements"]
            ) for c in companies
        ),
        "companies": companies,
        "warning": (
            "This is a retrieval/coverage audit only. It does not verify source "
            "truth, standardize accounting items, calculate TTM, or produce valuation."
        ),
    }
    target = RAW / "coverage_audit.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "source_archive": report["source_archive"],
        "companies": len(companies),
        "companies_with_any_rows": report["companies_with_any_rows"],
        "record_status_counts": dict(totals),
        "audit_file": str(target.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
