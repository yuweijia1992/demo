#!/usr/bin/env python3
"""Archive public A-share financial statements from Sina via AKShare.

This job intentionally archives source rows without guessing field mappings.
It does NOT label interim cumulative values as TTM and does NOT fabricate HK data.
"""
from __future__ import annotations
import json, re, time, hashlib
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data/china-stocks-financial-valuation.json"
OUT = ROOT / "data/raw-financials"
OUT.mkdir(parents=True, exist_ok=True)
SYMBOLS = ["资产负债表", "利润表", "现金流量表"]
SINA_PREFIX = {"SH": "sh", "SZ": "sz"}

def json_safe(v):
    try:
        if v is None: return None
        if hasattr(v, "item"): v = v.item()
        if str(v) in ("nan", "NaT", "<NA>"): return None
        return v
    except Exception:
        return str(v)

def main():
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    stocks = master.get("stocks", [])
    jobs, seen = [], set()
    for s in stocks:
        m = re.search(r"(\d{6})\.(SH|SZ)", s.get("code", ""))
        if not m:
            continue
        code, exch = m.group(1), m.group(2)
        if code in seen: continue
        seen.add(code)
        jobs.append({"code": code, "exchange": exch,
                     "company": s.get("name"), "master_code": s.get("code")})

    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records, errors = [], []
    for i, job in enumerate(jobs, 1):
        ticker = SINA_PREFIX[job["exchange"]] + job["code"]
        for statement in SYMBOLS:
            source_url = (
                "https://vip.stock.finance.sina.com.cn/corp/go.php/"
                f"vFD_FinanceSummary/stockid/{job['code']}/displaytype/4.phtml"
            )
            try:
                df = ak.stock_financial_report_sina(stock=ticker, symbol=statement)
                rows = []
                if df is not None and not df.empty:
                    for row in df.to_dict(orient="records"):
                        rows.append({str(k): json_safe(v) for k, v in row.items()})
                records.append({
                    **job, "provider": "Sina Finance via AKShare",
                    "statement": statement, "source_url": source_url,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "row_count": len(rows), "rows": rows,
                    "status": "retrieved" if rows else "empty"
                })
            except Exception as exc:
                errors.append({"code": job["code"], "company": job["company"],
                               "statement": statement, "error": repr(exc)})
                records.append({
                    **job, "provider": "Sina Finance via AKShare",
                    "statement": statement, "source_url": source_url,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "row_count": 0, "rows": [], "status": "error",
                    "error": repr(exc)
                })
            time.sleep(1.2)

    payload = {
        "schema_version": "1.0",
        "run_id": run,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "master_as_of": master.get("asOf"),
        "source_method": "AKShare stock_financial_report_sina; raw provider rows preserved",
        "scope": {"master_companies": len(stocks), "unique_a_share_codes": len(jobs),
                  "unique_hk_codes": len(hk_jobs), "statements": SYMBOLS,
                  "hk_period_modes": ["年度", "报告期"]},
        "records": records,
        "errors": errors
    }
    out_file = OUT / f"a_share_statements_{run}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    out_file.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    summary = {
        "run_id": run, "master_companies": len(stocks),
        "unique_a_share_codes": len(jobs), "statement_requests": len(records),
        "retrieved": sum(r["status"] == "retrieved" for r in records),
        "empty": sum(r["status"] == "empty" for r in records),
        "errors": len(errors), "raw_file": str(out_file.relative_to(ROOT)),
        "sha256": digest,
        "hk_scope_note": "HK primary listings and separate HK share classes require HKEXnews/company filing extraction; not substituted with A-share data."
    }
    (OUT / f"latest_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not records or sum(r["status"] == "retrieved" for r in records) == 0:
        raise SystemExit("No statement data retrieved; do not publish an empty archive as success.")

if __name__ == "__main__":
    main()
