#!/usr/bin/env python3
"""Archive raw A-share and Hong Kong financial statements via AKShare.

Raw provider rows are preserved. Interim cumulative figures are never labelled TTM.
This is a collection layer, not an audited-data or valuation layer.
"""
from __future__ import annotations
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak
from akshare.stock.issue import stock_finance_sina as sina_module
from akshare.stock.finance import stock_finance_hk_em as hk_module

# Bound HTTP calls: upstream helpers otherwise may wait indefinitely on a stalled source.
def _install_http_timeout(module):
    original_get = module.http.get
    def bounded_get(*args, **kwargs):
        kwargs.setdefault("timeout", 25)
        return original_get(*args, **kwargs)
    module.http.get = bounded_get

_install_http_timeout(sina_module)
_install_http_timeout(hk_module)

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data/china-stocks-financial-valuation.json"
OUT = ROOT / "data/raw-financials"
OUT.mkdir(parents=True, exist_ok=True)
SYMBOLS = ["资产负债表", "利润表", "现金流量表"]
SINA_PREFIX = {"SH": "sh", "SZ": "sz"}


def json_safe(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if str(value) in ("nan", "NaT", "<NA>"):
        return None
    return value


def frame_rows(frame):
    if frame is None or frame.empty:
        return []
    return [
        {str(key): json_safe(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def main():
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    stocks = master.get("stocks", [])

    a_jobs, a_seen = [], set()
    hk_jobs, hk_seen = [], set()
    for stock in stocks:
        code_text = stock.get("code", "")
        match_a = re.search(r"(\d{6})\.(SH|SZ)", code_text)
        if match_a:
            code, exchange = match_a.group(1), match_a.group(2)
            if code not in a_seen:
                a_seen.add(code)
                a_jobs.append({
                    "code": code, "exchange": exchange,
                    "company": stock.get("name"), "master_code": code_text,
                })
        match_hk = re.search(r"(\d{5})\.HK", code_text)
        if match_hk:
            code = match_hk.group(1)
            if code not in hk_seen:
                hk_seen.add(code)
                hk_jobs.append({
                    "code": code, "exchange": "HK",
                    "company": stock.get("name"), "master_code": code_text,
                })

    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records, errors = [], []

    # A-share: Sina Finance via AKShare.
    for job in a_jobs:
        ticker = SINA_PREFIX[job["exchange"]] + job["code"]
        source_url = (
            "https://vip.stock.finance.sina.com.cn/corp/go.php/"
            f"vFD_FinanceSummary/stockid/{job['code']}/displaytype/4.phtml"
        )
        for statement in SYMBOLS:
            print(f"A-share {job['code']} {statement}", flush=True)
            try:
                frame = ak.stock_financial_report_sina(
                    stock=ticker, symbol=statement
                )
                rows = frame_rows(frame)
                records.append({
                    **job, "provider": "Sina Finance via AKShare",
                    "statement": statement, "period_mode": "provider_default",
                    "source_url": source_url,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "row_count": len(rows), "rows": rows,
                    "status": "retrieved" if rows else "empty",
                })
            except Exception as exc:
                error = repr(exc)
                errors.append({
                    "code": job["code"], "company": job["company"],
                    "statement": statement, "error": error,
                })
                records.append({
                    **job, "provider": "Sina Finance via AKShare",
                    "statement": statement, "period_mode": "provider_default",
                    "source_url": source_url,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "row_count": 0, "rows": [], "status": "error",
                    "error": error,
                })
            time.sleep(1.2)

    # HK: Eastmoney HK endpoint via AKShare. Annual and report-period views
    # are kept separately because the latter may contain cumulative interim data.
    for job in hk_jobs:
        source_url = (
            "https://emweb.securities.eastmoney.com/PC_HKF10/FinancialAnalysis/"
            f"index?type=web&code={job['code']}"
        )
        for statement in SYMBOLS:
            for indicator in ["年度", "报告期"]:
                print(
                    f"HK {job['code']} {statement} {indicator}", flush=True
                )
                try:
                    frame = ak.stock_financial_hk_report_em(
                        stock=job["code"], symbol=statement,
                        indicator=indicator,
                    )
                    rows = frame_rows(frame)
                    records.append({
                        **job, "provider": "Eastmoney HK via AKShare",
                        "statement": statement, "period_mode": indicator,
                        "source_url": source_url,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "row_count": len(rows), "rows": rows,
                        "status": "retrieved" if rows else "empty",
                    })
                except Exception as exc:
                    error = repr(exc)
                    errors.append({
                        "code": job["code"], "company": job["company"],
                        "statement": statement, "period_mode": indicator,
                        "error": error,
                    })
                    records.append({
                        **job, "provider": "Eastmoney HK via AKShare",
                        "statement": statement, "period_mode": indicator,
                        "source_url": source_url,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "row_count": 0, "rows": [], "status": "error",
                        "error": error,
                    })
                time.sleep(1.2)

    payload = {
        "schema_version": "1.1",
        "run_id": run,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "master_as_of": master.get("asOf"),
        "source_method": (
            "AKShare Sina A-share + Eastmoney HK endpoints; raw rows preserved"
        ),
        "scope": {
            "master_companies": len(stocks),
            "unique_a_share_codes": len(a_jobs),
            "unique_hk_codes": len(hk_jobs),
            "statements": SYMBOLS,
            "hk_period_modes": ["年度", "报告期"],
        },
        "records": records,
        "errors": errors,
    }
    out_file = OUT / f"company_statements_{run}.json"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    out_file.write_text(serialized, encoding="utf-8")
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    summary = {
        "run_id": run,
        "master_companies": len(stocks),
        "unique_a_share_codes": len(a_jobs),
        "unique_hk_codes": len(hk_jobs),
        "statement_requests": len(records),
        "retrieved": sum(row["status"] == "retrieved" for row in records),
        "empty": sum(row["status"] == "empty" for row in records),
        "errors": len(errors),
        "raw_file": str(out_file.relative_to(ROOT)),
        "sha256": digest,
        "note": (
            "Raw source archive only. Verify against exchange/company filings; "
            "do not treat cumulative interim values as TTM."
        ),
    }
    (OUT / "latest_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if not records or summary["retrieved"] == 0:
        raise SystemExit("No statement data retrieved; archive is not successful.")


if __name__ == "__main__":
    main()
