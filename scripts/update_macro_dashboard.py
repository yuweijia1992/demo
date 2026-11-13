#!/usr/bin/env python3
"""Build a daily macro snapshot from public FRED CSV observations.
Missing series remain null; this script never fabricates or forward-fills values.
"""
import csv, io, json, os, urllib.request
from datetime import datetime, timezone

SERIES = {
    "us10y_nominal": ("DGS10", "US 10Y Treasury yield", "%"),
    "us10y_real": ("DFII10", "US 10Y real yield", "%"),
    "vix": ("VIXCLS", "VIX", "index"),
    "dxy_broad": ("DTWEXBGS", "US dollar broad index", "index"),
    "usdcny": ("DEXCHUS", "USD/CNY", "CNY per USD"),
    "brent": ("DCOILBRENTEU", "Brent crude", "USD/barrel"),
    "fed_funds": ("FEDFUNDS", "Federal funds effective rate", "%"),
    "us_cpi_yoy": ("CPIAUCSL", "US CPI index (level; not YoY)", "index"),
}
def latest(series_id):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series_id
    req = urllib.request.Request(url, headers={"User-Agent":"ym-investment-dashboard/1.0 contact: public-research"})
    with urllib.request.urlopen(req, timeout=25) as response:
        rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    for row in reversed(rows):
        value = row.get(series_id, "")
        if value and value not in (".", "ND", "nan"):
            try:
                return {"date": row.get("observation_date") or row.get("DATE"), "value": float(value)}
            except ValueError:
                pass
    return None

data = {}
errors = {}
for key, (sid, label, unit) in SERIES.items():
    try:
        obs = latest(sid)
        data[key] = {"series_id": sid, "label": label, "unit": unit, **(obs or {})}
    except Exception as exc:
        data[key] = {"series_id": sid, "label": label, "unit": unit, "value": None, "date": None}
        errors[key] = str(exc)[:240]

def alert(key, threshold, op, level, message):
    item = data.get(key, {})
    v = item.get("value")
    if v is None: return None
    hit = v >= threshold if op == ">=" else v <= threshold
    return {"level": level, "key": key, "value": v, "threshold": threshold, "message": message} if hit else None

alerts = [
    alert("vix", 30, ">=", "high", "VIX达到30：市场波动压力升高，检查组合风险与流动性。"),
    alert("us10y_real", 2.25, ">=", "medium", "美国10年期实际利率达到2.25%：重新检查长久期资产估值敏感性。"),
    alert("us10y_nominal", 5, ">=", "medium", "美国10年期名义收益率达到5%：检查利率与债券久期风险。"),
    alert("usdcny", 7.3, ">=", "medium", "USD/CNY达到7.30：检查人民币计价组合的汇率敞口。"),
    alert("brent", 100, ">=", "medium", "布伦特原油达到100美元：关注能源成本与通胀传导。"),
]
payload = {
    "schema_version": "1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "timezone": "UTC",
    "source": "Federal Reserve Bank of St. Louis FRED public CSV graph endpoint",
    "source_url": "https://fred.stlouisfed.org/",
    "series": data,
    "alerts": [x for x in alerts if x],
    "errors": errors,
    "limitations": [
        "FRED series update frequencies differ; latest observation dates are shown per series.",
        "VIX and Treasury yields may be delayed or have no observation on weekends/holidays.",
        "DXY uses the broad trade-weighted dollar index DTWEXBGS, not ICE DXY.",
        "CPIAUCSL is a seasonally adjusted index level; YoY inflation is not calculated in this snapshot.",
        "This dashboard is monitoring only, not a trading signal or investment recommendation."
    ]
}
os.makedirs("data", exist_ok=True)
with open("data/macro-dashboard.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print("Wrote macro snapshot; series:", len(data), "errors:", len(errors))
