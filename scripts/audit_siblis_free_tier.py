#!/usr/bin/env python3
"""Audit Siblis free-tier valuation coverage without republishing copyrighted data values.

The free API states that returned data are © Siblis Research and for non-commercial use.
This script records only endpoint availability, observation dates and counts, not valuation
values. Sparse month-end observations are never promoted to a continuous monthly series.
"""
import json, os, time, urllib.request
from datetime import datetime, timezone

BASE = "https://siblisresearch.supabase.co/functions/v1/free-data-api"
OUT = "data/index-valuation/siblis-free-tier-audit.json"

def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": "Mozilla/5.0 (compatible; InvestmentLabResearch/1.0)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

audit = {
    "schema_version": "1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "provider": "Siblis Research",
    "api_base": BASE,
    "documentation": "https://github.com/siblisresearch/global-equity-valuations-api",
    "license_note": "API data are © Siblis Research and provided for non-commercial use. This audit intentionally stores no valuation values.",
    "tier": "free",
    "coverage": {},
    "index_catalog": [],
    "errors": {},
    "decision": "Sparse free-tier month-end snapshots are cross-checks only; they do not qualify for 60/120-month rolling percentiles."
}
try:
    catalog = get("/v1/indices")
    audit["index_catalog"] = [
        {"ticker": x.get("ticker"), "index_name": x.get("index_name")}
        for x in catalog.get("indices", [])
        if any(k in (str(x.get("ticker",""))+" "+str(x.get("index_name",""))).lower()
               for k in ("nasdaq", "hang seng", "hong kong", "hsi"))
    ]
    tickers = [x.get("ticker") for x in audit["index_catalog"] if x.get("ticker")]
    if "NDX" not in tickers:
        tickers.append("NDX")
    if not any("hang seng" in str(x.get("index_name","")).lower() for x in audit["index_catalog"]):
        tickers.extend(["HSI", "HKG"])
except Exception as exc:
    audit["errors"]["index_catalog"] = str(exc)[:300]
    tickers = ["NDX", "HSI", "HKG"]

for ticker in sorted(set(tickers)):
    audit["coverage"][ticker] = {}
    for ratio in ("pe-trailing", "pe-forward", "cape", "pb"):
        key = f"{ticker}/{ratio}"
        try:
            result = get(f"/v1/{ticker}/{ratio}")
            rows = result.get("data", [])
            dates = sorted({r.get("trading_day (EOD)") for r in rows if r.get("trading_day (EOD)")})
            audit["coverage"][ticker][ratio] = {
                "status": "OK" if dates else "EMPTY",
                "observations": len(dates),
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
                "dates": dates,
                "continuous_monthly": False,
                "percentile_5y_eligible": len(dates) >= 60,
                "percentile_10y_eligible": len(dates) >= 120
            }
        except Exception as exc:
            audit["coverage"][ticker][ratio] = {"status": "UNAVAILABLE", "error": str(exc)[:240]}
        time.sleep(0.15)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".tmp", "w", encoding="utf-8") as f:
    json.dump(audit, f, ensure_ascii=False, indent=2)
os.replace(OUT + ".tmp", OUT)
print(json.dumps({"generated_at": audit["generated_at"], "coverage": audit["coverage"],
                  "errors": audit["errors"]}, ensure_ascii=False, indent=2))
