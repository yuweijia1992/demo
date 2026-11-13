#!/usr/bin/env python3
"""Build a macro snapshot from FRED public CSV; missing observations stay null."""
import csv, io, json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

SERIES = {
    "us10y_nominal": ("DGS10", "US 10Y Treasury yield", "%"),
    "us10y_real": ("DFII10", "US 10Y real yield", "%"),
    "vix": ("VIXCLS", "VIX", "index"),
    "dxy_broad": ("DTWEXBGS", "US dollar broad index", "index"),
    "usdcny": ("DEXCHUS", "USD/CNY", "CNY per USD"),
    "brent": ("DCOILBRENTEU", "Brent crude", "USD/barrel"),
    "fed_funds": ("FEDFUNDS", "Federal funds effective rate", "%"),
    "us_cpi_index": ("CPIAUCSL", "US CPI index (level)", "index"),
}

def latest(series_id):
    # Limit payload size; all monitored series need only the recent observation window.
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series_id + "&cosd=2018-01-01"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ym-investment-dashboard/1.1"})
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=18) as response:
                raw = response.read().decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(raw)))
            for row in reversed(rows):
                value = row.get(series_id, "")
                if value and value not in (".", "ND", "nan"):
                    return {"date": row.get("observation_date") or row.get("DATE"), "value": float(value)}
            raise ValueError("No numeric observations in response")
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1)
    raise last_error

data, errors = {}, {}
def fetch_one(item):
    key, (sid, label, unit) = item
    try:
        return key, {"series_id": sid, "label": label, "unit": unit, **latest(sid)}, None
    except Exception as exc:
        return key, {"series_id": sid, "label": label, "unit": unit, "value": None, "date": None}, str(exc)[:240]

with ThreadPoolExecutor(max_workers=8) as pool:
    futures = [pool.submit(fetch_one, item) for item in SERIES.items()]
    for future in as_completed(futures):
        key, observation, error = future.result()
        data[key] = observation
        if error:
            errors[key] = error
data = {key: data[key] for key in SERIES}

def alert(key, threshold, level, message):
    item = data.get(key, {})
    value = item.get("value")
    if value is not None and value >= threshold:
        return {"level": level, "key": key, "value": value, "threshold": threshold, "message": message}
    return None

alerts = [
    alert("vix", 30, "high", "VIX达到30：市场波动压力升高，检查组合风险与流动性。"),
    alert("us10y_real", 2.25, "medium", "美国10年期实际利率达到2.25%：重新检查长久期资产估值敏感性。"),
    alert("us10y_nominal", 5, "medium", "美国10年期名义收益率达到5%：检查利率与债券久期风险。"),
    alert("usdcny", 7.3, "medium", "USD/CNY达到7.30：检查人民币计价组合的汇率敞口。"),
    alert("brent", 100, "medium", "布伦特原油达到100美元：关注能源成本与通胀传导。"),
]
payload = {
    "schema_version": "1.1",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "timezone": "UTC",
    "status": "ok" if not errors else ("partial" if len(errors) < len(SERIES) else "error"),
    "source": "Federal Reserve Bank of St. Louis FRED public CSV graph endpoint",
    "source_url": "https://fred.stlouisfed.org/",
    "series": data,
    "alerts": [x for x in alerts if x],
    "errors": errors,
    "limitations": [
        "FRED series update frequencies differ; latest observation dates are shown per series.",
        "VIX and Treasury yields may be delayed or have no observation on weekends/holidays.",
        "DXY uses the broad trade-weighted dollar index DTWEXBGS, not ICE DXY.",
        "CPIAUCSL is a seasonally adjusted index level; it is not year-over-year inflation.",
        "This dashboard is monitoring only, not a trading signal or investment recommendation."
    ]
}
os.makedirs("data", exist_ok=True)
with open("data/macro-dashboard.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print("Wrote macro snapshot; series:", len(data), "successful:", len(data)-len(errors), "errors:", len(errors))
