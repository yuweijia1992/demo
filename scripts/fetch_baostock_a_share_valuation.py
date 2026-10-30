#!/usr/bin/env python3
"""Fetch pre-2018 daily A-share PE-TTM/PB-MRQ/PS-TTM from BaoStock.

Public BaoStock query_history_k_data_plus supports daily valuation fields.
No personal API token is required. Rows are kept with explicit source provenance.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import baostock as bs

SOURCE_LABEL = "BaoStock / query_history_k_data_plus"
SOURCE_URL = "https://github.com/baostock/baostock/blob/master/docs/pythonAPI.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--output", default="data/valuation-history/raw/baostock-pre2018-daily.csv")
    parser.add_argument("--audit", default="data/valuation-history/raw/baostock-fetch-audit.json")
    parser.add_argument("--start-date", default="2006-01-01")
    parser.add_argument("--end-date", default="2017-12-31")
    parser.add_argument("--pause", type=float, default=0.15)
    args = parser.parse_args()

    universe_path = Path(args.universe)
    if not universe_path.exists():
        parser.error(f"universe file not found: {universe_path}")
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    securities = [
        item for item in universe.get("securities", [])
        if item.get("market") == "CN"
        and str(item.get("securityCode", "")).endswith((".SH", ".SZ"))
    ]
    if not securities:
        parser.error("universe contains no A-share securities")

    output_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    login = bs.login()
    if getattr(login, "error_code", "") != "0":
        error = (
            "BaoStock login failed: "
            + str(getattr(login, "error_code", "unknown"))
            + " "
            + str(getattr(login, "error_msg", "unknown"))
        )
        failures.append({"scope": "login", "error": error})
        audits = [
            {"code": str(item["securityCode"]), "rows": 0, "status": "ERROR", "error": error}
            for item in securities
        ]
    else:
        try:
            for index, security in enumerate(securities, start=1):
                full_code = str(security["securityCode"])
                digits, market = full_code.split(".")
                bs_code = ("sh." if market == "SH" else "sz.") + digits
                print(f"[{index}/{len(securities)}] BaoStock {security['issuerName']} {full_code}", flush=True)

                try:
                    result = bs.query_history_k_data_plus(
                        bs_code,
                        "date,code,close,peTTM,pbMRQ,psTTM",
                        start_date=args.start_date,
                        end_date=args.end_date,
                        frequency="d",
                        adjustflag="3",
                    )
                    if getattr(result, "error_code", "") != "0":
                        raise RuntimeError(
                            str(getattr(result, "error_code", "unknown"))
                            + " "
                            + str(getattr(result, "error_msg", "unknown"))
                        )

                    count = 0
                    while result.next():
                        values = result.get_row_data()
                        if len(values) < 6:
                            continue
                        day, _, close, pe, pb, ps = values[:6]
                        if not day:
                            continue
                        output_rows.append({
                            "code": full_code,
                            "date": day,
                            "close": close,
                            "currency": "CNY",
                            "peTtm": pe,
                            "pb": pb,
                            "psTtm": ps,
                            "source": SOURCE_LABEL,
                            "sourceUrl": SOURCE_URL,
                        })
                        count += 1

                    audits.append({
                        "code": full_code,
                        "baoStockCode": bs_code,
                        "rows": count,
                        "startDate": args.start_date,
                        "endDate": args.end_date,
                        "status": "OK" if count else "EMPTY",
                        "sourceUrl": SOURCE_URL,
                    })
                    if count == 0:
                        failures.append({"code": full_code, "error": "no rows in requested historical period"})
                    print(f"  {count} daily rows", flush=True)
                except Exception as exc:
                    failures.append({"code": full_code, "error": str(exc)})
                    audits.append({
                        "code": full_code,
                        "baoStockCode": bs_code,
                        "rows": 0,
                        "status": "ERROR",
                        "error": str(exc),
                        "sourceUrl": SOURCE_URL,
                    })
                    print(f"  ERROR: {exc}", flush=True)
                time.sleep(max(0.0, args.pause))
        finally:
            bs.logout()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["code", "date", "close", "currency", "peTtm", "pb", "psTtm", "source", "sourceUrl"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(output_rows, key=lambda x: (x["code"], x["date"])))

    audit_doc = {
        "source": SOURCE_LABEL,
        "sourceUrl": SOURCE_URL,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "startDate": args.start_date,
        "endDate": args.end_date,
        "requestedAshareCompanies": len(securities),
        "companiesWithRows": sum(1 for x in audits if x.get("rows", 0) > 0),
        "dailyRows": len(output_rows),
        "failedOrEmptyCompanies": failures,
        "securities": audits,
        "note": "BaoStock daily valuation indicators. Missing and non-positive valuation values remain blank; no forward filling or interpolation.",
    }
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "requested": len(securities),
        "withRows": audit_doc["companiesWithRows"],
        "dailyRows": len(output_rows),
        "failedOrEmpty": failures,
        "csv": str(output_path),
        "audit": str(audit_path),
    }, ensure_ascii=False, indent=2))
    # Keep the audit and continue to the Eastmoney source even if BaoStock is partially unavailable.
    return 0


if __name__ == "__main__":
    sys.exit(main())
